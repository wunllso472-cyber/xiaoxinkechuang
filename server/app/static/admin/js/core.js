/* 公共：API 请求、通用组件（图表、通用增删改查页） */
const { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick, h } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;
window.Pages = {};

const store = reactive({
  token: localStorage.getItem('xx_token') || '',
  user: JSON.parse(localStorage.getItem('xx_user') || 'null'),
});

async function api(url, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (store.token) headers['Authorization'] = 'Bearer ' + store.token;
  let body = opts.body;
  if (body && !(body instanceof FormData) && typeof body !== 'string') {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }
  let q = '';
  if (opts.params) {
    const p = Object.entries(opts.params).filter(([, v]) => v !== '' && v !== null && v !== undefined);
    if (p.length) q = '?' + new URLSearchParams(p).toString();
  }
  const res = await fetch(url + q, { method: opts.method || (body ? 'POST' : 'GET'), headers, body });
  if (res.status === 401) {
    store.token = ''; localStorage.removeItem('xx_token');
    throw new Error('登录已过期');
  }
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (data && data.detail) ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : ('请求失败 ' + res.status);
    ElMessage.error(msg);
    throw new Error(msg);
  }
  return data;
}
api.get = (u, params) => api(u, { params });
api.post = (u, body) => api(u, { method: 'POST', body: body || {} });
api.put = (u, body) => api(u, { method: 'PUT', body });
api.del = (u) => api(u, { method: 'DELETE' });

/* 流式 SSE 读取（fetch + ReadableStream），返回 AbortController */
function streamPost(url, body, onEvent, extraHeaders) {
  const ctrl = new AbortController();
  const headers = Object.assign({ 'Content-Type': 'application/json' }, extraHeaders || {});
  if (store.token) headers['Authorization'] = 'Bearer ' + store.token;
  fetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal: ctrl.signal }).then(async (res) => {
    if (!res.ok) { onEvent({ type: 'error', text: '请求失败 ' + res.status }); return; }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 2);
        if (line.startsWith('data:')) { try { onEvent(JSON.parse(line.slice(5))); } catch (e) { } }
      }
    }
    onEvent({ type: 'end' });
  }).catch((e) => onEvent({ type: e.name === 'AbortError' ? 'aborted' : 'error', text: String(e) }));
  return ctrl;
}

const fmtSize = (b) => { if (!b) return '0'; const u = ['B', 'KB', 'MB', 'GB']; let i = 0; while (b >= 1024 && i < 3) { b /= 1024; i++; } return b.toFixed(1) + u[i]; };
const ROLE = { admin: '管理员', cs: '客服', ops: '运维', user: '普通用户' };

/* ECharts 组件 */
const EChart = {
  props: { option: Object, height: { type: String, default: '280px' } },
  setup(props) {
    const el = ref(null); let chart = null; let ro = null;
    const render = () => { if (chart && props.option) chart.setOption(Object.assign({ color: PALETTE }, props.option), true); };
    onMounted(() => {
      chart = echarts.init(el.value); render();
      ro = new ResizeObserver(() => chart && chart.resize()); ro.observe(el.value);
    });
    watch(() => props.option, render, { deep: true });
    onBeforeUnmount(() => { ro && ro.disconnect(); chart && chart.dispose(); });
    return { el };
  },
  template: `<div ref="el" :style="{width:'100%',height:height}"></div>`,
};

/* 图表配色与平台主色保持一致 */
const PALETTE = ['#1664ff', '#14c9c9', '#ff7d00', '#00b42a', '#722ed1', '#f7ba1e', '#f53f3f', '#3491fa', '#a9aeb8'];
const charts = {
  pie: (data, title) => ({ title: title ? { text: title, left: 'center', textStyle: { fontSize: 14 } } : undefined, tooltip: { trigger: 'item' }, legend: { bottom: 0, type: 'scroll' }, series: [{ type: 'pie', radius: ['40%', '65%'], data, label: { formatter: '{b}: {c}' } }] }),
  bar: (labels, series, opts = {}) => ({ tooltip: { trigger: 'axis' }, legend: { top: 0 }, grid: { left: 40, right: 20, bottom: 30, top: 36, containLabel: true }, xAxis: { type: 'category', data: labels, axisLabel: { interval: 0, rotate: labels.length > 8 ? 30 : 0 } }, yAxis: { type: 'value', ...(opts.yAxis || {}) }, series: series.map(s => ({ type: 'bar', barMaxWidth: 28, ...s })) }),
  line: (labels, series, opts = {}) => ({ tooltip: { trigger: 'axis' }, legend: { top: 0 }, grid: { left: 40, right: 20, bottom: 30, top: 36, containLabel: true }, xAxis: { type: 'category', data: labels, boundaryGap: false }, yAxis: { type: 'value', ...(opts.yAxis || {}) }, series: series.map(s => ({ type: 'line', smooth: true, symbolSize: 4, ...s })) }),
};

/* 通用增删改查页
 * columns: [{prop,label,type:'text|textarea|number|bool|select|datetime|json|password',options:[{label,value}],width,list:true,form:true,required}]
 */
const CrudPage = {
  props: { title: String, api: String, columns: Array, filters: { type: Array, default: () => [] }, searchable: { type: Boolean, default: true },
    readonly: Boolean, defaults: { type: Object, default: () => ({}) }, rowActions: { type: Array, default: () => [] }, toolActions: { type: Array, default: () => [] },
    dialogWidth: { type: String, default: '620px' } },
  setup(props, { expose }) {
    const rows = ref([]); const total = ref(0); const loading = ref(false);
    const query = reactive({ page: 1, page_size: 20, keyword: '' });
    props.filters.forEach(f => query[f.prop] = '');
    const dlg = reactive({ show: false, data: {}, editing: false });
    const listCols = computed(() => props.columns.filter(c => c.list !== false));
    const formCols = computed(() => props.columns.filter(c => c.form !== false));
    const load = async () => {
      loading.value = true;
      try { const r = await api.get(props.api, query); rows.value = r.items; total.value = r.total; } finally { loading.value = false; }
    };
    const optLabel = (c, v) => { const o = (c.options || []).find(o => o.value === v); return o ? o.label : v; };
    const display = (c, row) => {
      const v = row[c.prop];
      if (c.formatter) return c.formatter(v, row);
      if (c.type === 'bool') return v ? '是' : '否';
      if (c.type === 'select') return optLabel(c, v);
      if (c.type === 'json') return v == null ? '' : JSON.stringify(v).slice(0, 80);
      return v;
    };
    const open = (row) => {
      const d = {};
      formCols.value.forEach(c => {
        let v = row ? row[c.prop] : (props.defaults[c.prop] !== undefined ? props.defaults[c.prop] : (c.type === 'bool' ? false : (c.type === 'json' ? null : '')));
        if (c.type === 'json') v = v == null ? '' : JSON.stringify(v, null, 2);
        d[c.prop] = v;
      });
      if (row) d.__id = row.id !== undefined ? row.id : row.key;
      dlg.data = d; dlg.editing = !!row; dlg.show = true;
    };
    const save = async () => {
      const d = {};
      for (const c of formCols.value) {
        let v = dlg.data[c.prop];
        if (c.required && (v === '' || v == null)) { ElMessage.warning('请填写' + c.label); return; }
        if (c.type === 'json') { try { v = v ? JSON.parse(v) : null; } catch (e) { ElMessage.error(c.label + ' 不是合法 JSON'); return; } }
        d[c.prop] = v;
      }
      if (dlg.editing) await api.put(props.api + '/' + dlg.data.__id, d); else await api.post(props.api, d);
      ElMessage.success('保存成功'); dlg.show = false; load();
    };
    const remove = async (row) => {
      await ElMessageBox.confirm('确定删除该记录？', '提示', { type: 'warning' });
      await api.del(props.api + '/' + (row.id !== undefined ? row.id : row.key)); ElMessage.success('已删除'); load();
    };
    const reset = () => { query.keyword = ''; props.filters.forEach(f => query[f.prop] = ''); query.page = 1; load(); };
    onMounted(load);
    expose({ load });
    return { rows, total, loading, query, dlg, listCols, formCols, load, reset, open, save, remove, display };
  },
  template: `
  <div class="card">
    <div class="toolbar">
      <el-input v-if="searchable" v-model="query.keyword" placeholder="请输入关键字" clearable @keyup.enter="query.page=1;load()" />
      <template v-for="f in filters" :key="f.prop">
        <el-select v-model="query[f.prop]" :placeholder="'请选择' + f.label" clearable @change="query.page=1;load()">
          <el-option v-for="o in f.options" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </template>
      <span class="spacer"></span>
      <el-button @click="reset">重 置</el-button>
      <el-button type="primary" @click="query.page=1;load()">搜 索</el-button>
    </div>
    <div class="toolbar" v-if="!readonly || toolActions.length || $slots.toolbar">
      <el-button v-if="!readonly" type="primary" @click="open(null)">新 增</el-button>
      <el-button v-for="a in toolActions" :key="a.label" :type="a.type||'default'" @click="a.click(load)">{{a.label}}</el-button>
      <slot name="toolbar" :load="load"></slot>
    </div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column type="index" label="序号" width="64" align="center" :index="i => (query.page-1)*query.page_size + i + 1" />
      <el-table-column v-for="c in listCols" :key="c.prop" :prop="c.prop" :label="c.label" :width="c.width" :min-width="c.minWidth||100" show-overflow-tooltip>
        <template #default="{row}">
          <el-tag v-if="c.tag" size="small" :type="c.tag(row[c.prop], row)">{{display(c,row)}}</el-tag>
          <span v-else>{{display(c,row)}}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" :width="120 + rowActions.length*60" fixed="right">
        <template #default="{row}">
          <el-button v-for="a in rowActions" :key="a.label" link :type="a.type||'primary'" v-show="!a.show || a.show(row)" @click="a.click(row, load)">{{a.label}}</el-button>
          <el-button v-if="!readonly" link type="primary" @click="open(row)">编辑</el-button>
          <el-button v-if="!readonly" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination layout="total, prev, pager, next, sizes, jumper" :total="total" v-model:current-page="query.page" v-model:page-size="query.page_size" @current-change="load" @size-change="load" />
    <el-dialog v-model="dlg.show" :title="(dlg.editing?'编辑':'新增') + (title||'')" :width="dialogWidth" destroy-on-close>
      <el-form label-width="130px" size="default">
        <el-form-item v-for="c in formCols" :key="c.prop" :label="c.label" :required="c.required">
          <el-switch v-if="c.type==='bool'" v-model="dlg.data[c.prop]" />
          <el-select v-else-if="c.type==='select'" v-model="dlg.data[c.prop]" style="width:100%" :allow-create="c.allowCreate" filterable>
            <el-option v-for="o in c.options" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-input-number v-else-if="c.type==='number'" v-model="dlg.data[c.prop]" :step="c.step||1" :min="c.min" :max="c.max" />
          <el-date-picker v-else-if="c.type==='datetime'" v-model="dlg.data[c.prop]" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" />
          <el-input v-else-if="c.type==='textarea'||c.type==='json'" v-model="dlg.data[c.prop]" type="textarea" :rows="c.rows || (c.type==='json'?6:3)" :placeholder="c.placeholder" />
          <el-input v-else-if="c.type==='password'" v-model="dlg.data[c.prop]" type="password" show-password :placeholder="c.placeholder" />
          <el-input v-else v-model="dlg.data[c.prop]" :placeholder="c.placeholder" />
          <div v-if="c.tip" class="muted">{{c.tip}}</div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="dlg.show=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>`,
};

const opts = (arr) => arr.map(x => Array.isArray(x) ? { value: x[0], label: x[1] } : { value: x, label: x });
const boolOpts = [{ value: 'true', label: '是' }, { value: 'false', label: '否' }];

/* 智能运维 */
const T_STATUS = ['待指派', '待签收', '处理中', '挂起审核中', '待评价', '已办结'];
const T_CAT = ['终端故障', '打印外设', '网络', '操作系统', '办公软件', '账号权限', '智能报修', '其他'];
const statusType = (s) => ({ 待指派: 'danger', 待签收: 'warning', 处理中: '', 挂起审核中: 'warning', 待评价: 'info', 已办结: 'success' })[s] || 'info';

/* 工单详情抽屉（工作台与工单池共用） */
const TicketDrawer = {
  props: { modelValue: Boolean, id: Number },
  emits: ['update:modelValue', 'changed'],
  setup(props, { emit }) {
    const t = ref(null); const staff = ref([]);
    const load = async () => { if (props.id) t.value = await api.get('/api/ops/tickets/' + props.id); };
    watch(() => [props.id, props.modelValue], () => props.modelValue && load());
    onMounted(async () => { staff.value = await api.get('/api/staff', { role: 'ops' }); });
    const done = () => { load(); emit('changed'); };
    const assign = async (aid) => { await api.post('/api/ops/tickets/' + t.value.id + '/assign', { assignee_id: aid }); ElMessage.success('已指派'); done(); };
    const audit = async (approve) => { await api.post('/api/ops/tickets/' + t.value.id + '/suspend-audit', { approve }); done(); };
    const close = async () => { await api.post('/api/ops/tickets/' + t.value.id + '/close', {}); done(); };
    const rate = async () => { const { value } = await ElMessageBox.prompt('请输入用户评分(1-5)', '用户评价', { inputValue: '5' }); await api.post('/api/ops/tickets/' + t.value.id + '/rate', { rating: +value }); done(); };
    const toCase = async () => { await api.post('/api/ops/tickets/' + t.value.id + '/to-case', {}); ElMessage.success('已上报案例，待审核'); };
    return { t, staff, assign, audit, close, rate, toCase, statusType, emit };
  },
  template: `<el-drawer :model-value="modelValue" @update:model-value="v=>emit('update:modelValue',v)" size="50%" title="工单详情">
    <template v-if="t">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="工单号">{{t.ticket_no}}</el-descriptions-item><el-descriptions-item label="状态"><el-tag :type="statusType(t.status)">{{t.status}}</el-tag></el-descriptions-item>
        <el-descriptions-item label="标题" :span="2">{{t.title}}</el-descriptions-item><el-descriptions-item label="描述" :span="2">{{t.description}}</el-descriptions-item>
        <el-descriptions-item label="分类">{{t.category}}</el-descriptions-item><el-descriptions-item label="来源">{{t.source}}</el-descriptions-item>
        <el-descriptions-item label="报修人">{{t.reporter}} {{t.reporter_phone}}</el-descriptions-item><el-descriptions-item label="部门/地点">{{t.dept}} {{t.address}}</el-descriptions-item>
        <el-descriptions-item label="设备">{{t.device_info}}</el-descriptions-item><el-descriptions-item label="处理人">{{t.assignee_name}}</el-descriptions-item>
        <el-descriptions-item label="反馈期限">{{t.deadline}}</el-descriptions-item><el-descriptions-item label="评价">{{t.rating ? t.rating+'星 '+t.rating_comment : ''}}</el-descriptions-item>
        <el-descriptions-item label="解决方案" :span="2">{{t.solution}}</el-descriptions-item>
        <el-descriptions-item v-if="t.suspend_reason" label="挂起原因" :span="2">{{t.suspend_reason}}（申请延期 {{t.suspend_days}} 天）</el-descriptions-item>
      </el-descriptions>
      <div style="margin:14px 0;display:flex;gap:8px;flex-wrap:wrap">
        <el-select v-if="['待指派','待签收'].includes(t.status)" placeholder="指派运维人员" @change="assign" style="width:200px"><el-option v-for="s in staff" :key="s.id" :value="s.id" :label="s.name + '（' + s.station + (s.company?'/'+s.company:'') + '）'"/></el-select>
        <template v-if="t.status==='挂起审核中'"><el-button type="success" @click="audit(true)">挂起审核通过</el-button><el-button type="danger" @click="audit(false)">驳回挂起</el-button></template>
        <el-button v-if="t.status==='待评价'" type="primary" @click="rate">录入用户评价</el-button>
        <el-button v-if="t.status!=='已办结'" @click="close">直接办结</el-button>
        <el-button v-if="['待评价','已办结'].includes(t.status)" @click="toCase">上报为案例</el-button>
      </div>
      <h4>流转记录</h4>
      <el-timeline><el-timeline-item v-for="l in t.logs" :key="l.id" :timestamp="l.created_at">{{l.operator}} · {{l.action}} <span class="muted">{{l.content}}</span></el-timeline-item></el-timeline>
    </template>
  </el-drawer>`,
};

Pages.workbench = {
  components: { EChart, TicketDrawer },
  setup() {
    const d = ref(null); const drawer = ref(false); const tid = ref(null);
    const load = async () => { d.value = await api.get('/api/ops/workbench'); };
    const open = (id) => { tid.value = id; drawer.value = true; };
    onMounted(load);
    return { d, load, drawer, tid, open, charts, statusType };
  },
  template: `<div v-if="d">
    <div class="stat-row"><div v-for="(v,k) in d.counts" :key="k" class="stat" :class="{danger:k==='待指派'&&v>0, warn:k==='挂起审核中'&&v>0}"><div class="l">{{k}}</div><div class="v">{{v}}</div></div>
      <div class="stat warn"><div class="l">待审核案例</div><div class="v">{{d.case_pending}}</div></div></div>
    <div class="grid2">
      <div class="card"><h3>工单预警</h3>
        <el-empty v-if="!d.warnings.length" description="暂无预警" :image-size="60"/>
        <div v-for="w in d.warnings" :key="w.type+w.id" style="padding:6px 0;border-bottom:1px dashed #eee;cursor:pointer" @click="open(w.id)">
          <el-tag size="small" :type="w.type==='待指派超时'?'danger':'warning'">{{w.type}}</el-tag> {{w.ticket_no}} {{w.title}}</div></div>
      <div class="card"><h3>近7日工单趋势</h3><e-chart height="240px" :option="charts.line(d.trend.map(x=>x.day),[{name:'新增',data:d.trend.map(x=>x.created)},{name:'办结',data:d.trend.map(x=>x.finished)}])"/></div>
    </div>
    <div class="card"><h3>我的待办（快捷入口）</h3>
      <el-table :data="d.todo" size="small" border @row-click="r=>open(r.id)"><el-table-column prop="ticket_no" label="工单号" width="170"/><el-table-column prop="title" label="标题"/>
        <el-table-column label="状态" width="100"><template #default="{row}"><el-tag size="small" :type="statusType(row.status)">{{row.status}}</el-tag></template></el-table-column>
        <el-table-column prop="assignee_name" label="处理人" width="100"/><el-table-column prop="created_at" label="创建时间" width="160"/></el-table></div>
    <ticket-drawer v-model="drawer" :id="tid" @changed="load"/>
  </div>`,
};

Pages.register = {
  setup() {
    const empty = () => ({ title: '', description: '', category: '终端故障', reporter: '', reporter_phone: '', dept: '', address: '', device_info: '', status: '待指派', assignee_id: null, solution: '' });
    const f = ref(empty()); const staff = ref([]); const kw = ref(''); const cases = ref([]); const cur = ref(null);
    const search = async () => { cases.value = await api.get('/api/ops/case-search', { keyword: kw.value || f.value.title }); };
    const view = async (c) => { cur.value = await api.post('/api/ops/cases/' + c.id + '/view'); };
    const submit = async () => {
      if (!f.value.title) return ElMessage.warning('请填写问题标题');
      const t = await api.post('/api/ops/tickets', f.value);
      ElMessage.success((f.value.status === '已办结' ? '补录工单成功：' : '登记成功：') + t.ticket_no); f.value = empty();
    };
    onMounted(async () => { staff.value = await api.get('/api/staff', { role: 'ops' }); });
    return { f, staff, kw, cases, search, view, cur, submit, T_CAT };
  },
  template: `<div class="grid2">
    <div class="card"><h3>来电问题登记</h3>
      <el-form label-width="90px">
        <el-form-item label="问题标题" required><el-input v-model="f.title" @blur="!kw && f.title && search()"/></el-form-item>
        <el-form-item label="问题描述"><el-input v-model="f.description" type="textarea" :rows="3"/></el-form-item>
        <el-form-item label="问题分类"><el-select v-model="f.category"><el-option v-for="c in T_CAT" :key="c" :value="c" :label="c"/></el-select></el-form-item>
        <el-form-item label="报修人"><el-input v-model="f.reporter" style="width:45%"/>&nbsp;<el-input v-model="f.reporter_phone" placeholder="联系电话" style="width:45%"/></el-form-item>
        <el-form-item label="部门/地点"><el-input v-model="f.dept" placeholder="部门" style="width:45%"/>&nbsp;<el-input v-model="f.address" placeholder="地点" style="width:45%"/></el-form-item>
        <el-form-item label="设备信息"><el-input v-model="f.device_info"/></el-form-item>
        <el-form-item label="问题状态"><el-radio-group v-model="f.status"><el-radio value="待指派">待处理（进入指派流转）</el-radio><el-radio value="已办结">已办结（补录，不流转）</el-radio></el-radio-group></el-form-item>
        <el-form-item v-if="f.status!=='已办结'" label="直接指派"><el-select v-model="f.assignee_id" clearable placeholder="可选"><el-option v-for="s in staff" :key="s.id" :value="s.id" :label="s.name+'（'+s.station+'）'"/></el-select></el-form-item>
        <el-form-item v-else label="解决方案"><el-input v-model="f.solution" type="textarea"/></el-form-item>
        <el-form-item><el-button type="primary" @click="submit">提交登记</el-button></el-form-item>
      </el-form></div>
    <div class="card"><h3>案例检索（故障解决方案参考）</h3>
      <div class="toolbar"><el-input v-model="kw" placeholder="输入关键字检索已审核案例" clearable @keyup.enter="search" style="width:260px"/><el-button type="primary" @click="search">检索</el-button></div>
      <div v-for="c in cases" :key="c.id" style="padding:8px;border-bottom:1px solid #f0f0f0;cursor:pointer" @click="view(c)">
        <el-tag v-if="c.quality" size="small" type="success">高质量</el-tag> <b>{{c.title}}</b> <span class="muted">{{c.category}} · 浏览{{c.view_count}}</span></div>
      <el-empty v-if="!cases.length" description="暂无匹配案例" :image-size="60"/>
      <el-dialog :model-value="!!cur" @update:model-value="cur=null" :title="cur && cur.title" width="560px"><template v-if="cur"><p><b>问题：</b>{{cur.question}}</p><p style="white-space:pre-wrap"><b>解决方案：</b>{{cur.answer}}</p></template></el-dialog>
    </div></div>`,
};

Pages.tickets = {
  components: { TicketDrawer },
  setup() {
    const rows = ref([]); const total = ref(0); const q = reactive({ page: 1, keyword: '', status: '', category: '', source: '', start: '', end: '' });
    const drawer = ref(false); const tid = ref(null); const range = ref([]);
    const load = async () => { q.start = range.value && range.value[0] || ''; q.end = range.value && range.value[1] || ''; const r = await api.get('/api/ops/tickets', q); rows.value = r.items; total.value = r.total; };
    onMounted(load);
    return { rows, total, q, load, drawer, tid, range, T_STATUS, T_CAT, statusType, open: (r) => { tid.value = r.id; drawer.value = true; } };
  },
  template: `<div class="card"><div class="toolbar"><el-input v-model="q.keyword" placeholder="工单号/标题/报修人/电话" clearable/>
    <el-select v-model="q.status" placeholder="状态" clearable><el-option v-for="s in T_STATUS" :key="s" :value="s" :label="s"/></el-select>
    <el-select v-model="q.category" placeholder="分类" clearable><el-option v-for="s in T_CAT" :key="s" :value="s" :label="s"/></el-select>
    <el-select v-model="q.source" placeholder="来源" clearable><el-option v-for="s in ['来电','补录','移动登记','移动补录','智能问答']" :key="s" :value="s" :label="s"/></el-select>
    <el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始" end-placeholder="结束" style="width:240px"/>
    <el-button type="primary" @click="q.page=1;load()">搜索</el-button></div>
    <el-table :data="rows" border size="small"><el-table-column prop="ticket_no" label="工单号" width="170"/><el-table-column prop="title" label="标题" min-width="150"/>
      <el-table-column prop="category" label="分类" width="90"/><el-table-column prop="source" label="来源" width="80"/><el-table-column prop="reporter" label="报修人" width="80"/>
      <el-table-column label="状态" width="100"><template #default="{row}"><el-tag size="small" :type="statusType(row.status)">{{row.status}}</el-tag></template></el-table-column>
      <el-table-column prop="assignee_name" label="处理人" width="90"/><el-table-column prop="station" label="保障站" width="100"/><el-table-column prop="created_at" label="创建时间" width="155"/>
      <el-table-column label="操作" width="70"><template #default="{row}"><el-button link type="primary" @click="open(row)">详情</el-button></template></el-table-column></el-table>
    <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load"/>
    <ticket-drawer v-model="drawer" :id="tid" @changed="load"/></div>`,
};

Pages.cases = {
  components: { CrudPage },
  setup() {
    const cols = [{ prop: 'title', label: '案例标题', required: true, minWidth: 160 }, { prop: 'category', label: '问题类型', type: 'select', allowCreate: true, options: opts(T_CAT) },
      { prop: 'question', label: '问题描述', type: 'textarea', list: false }, { prop: 'answer', label: '解答详情', type: 'textarea', rows: 6, list: false },
      { prop: 'status', label: '状态', type: 'select', options: opts(['待审核', '已通过', '已驳回']), tag: v => v === '已通过' ? 'success' : v === '待审核' ? 'warning' : 'danger' },
      { prop: 'quality', label: '高质量案例', type: 'bool' }, { prop: 'reporter', label: '上报人', form: false }, { prop: 'station', label: '保障站', form: false },
      { prop: 'view_count', label: '浏览', form: false, width: 60 }, { prop: 'audit_comment', label: '审核意见', form: false }];
    const audit = (approve) => async (row, load) => {
      const { value } = await ElMessageBox.prompt('审核意见', approve ? '审核通过' : '驳回', { inputValue: approve ? '同意纳入案例库' : '' });
      await api.post('/api/ops/cases/' + row.id + '/audit', { approve, comment: value }); load();
    };
    const actions = [{ label: '通过', type: 'success', show: r => r.status === '待审核', click: audit(true) }, { label: '驳回', type: 'danger', show: r => r.status === '待审核', click: audit(false) }];
    return { cols, actions, filters: [{ prop: 'status', label: '状态', options: opts(['待审核', '已通过', '已驳回']) }, { prop: 'category', label: '类型', options: opts(T_CAT) }] };
  },
  template: `<div><el-alert type="info" :closable="false" style="margin-bottom:12px" title="区县保障站上报的典型工单案例需市保障中心管理员审核，审核通过后纳入案例库供客服检索。"/>
    <crud-page api="/api/ops/cases" title="案例" :columns="cols" :filters="filters" :row-actions="actions" :defaults="{status:'已通过',category:'终端故障'}"/></div>`,
};

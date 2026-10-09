/* 终端资源管理 / 终端运行监测 / 客户端管理 / 消息管理 */

Pages.dashboard = {
  components: { EChart },
  setup() {
    const ov = ref(null); const ind = ref(null); const act = ref(null);
    onMounted(async () => {
      ov.value = await api.get('/api/admin/overview');
      ind.value = (await api.get('/api/admin/indicators')).overall;
      act.value = await api.get('/api/admin/activity', { period: 'day', n: 14 });
    });
    return { ov, ind, act, charts };
  },
  template: `<div v-if="ov">
    <div class="stat-row">
      <div class="stat"><div class="l">接入终端总数</div><div class="v">{{ov.total}}</div></div>
      <div class="stat ok"><div class="l">在线终端</div><div class="v">{{ov.online}}</div></div>
      <div class="stat"><div class="l">离线终端</div><div class="v">{{ov.offline}}</div></div>
      <div class="stat ok"><div class="l">信创终端</div><div class="v">{{ov.xinchuang}}</div></div>
      <div class="stat"><div class="l">云桌面终端</div><div class="v">{{ov.cloud_desktop}}</div></div>
      <div class="stat danger"><div class="l">未处理预警</div><div class="v">{{ov.alerts_open}}</div></div>
    </div>
    <div class="stat-row" v-if="ind">
      <div class="stat" :class="ind['接入率']<90?'warn':'ok'"><div class="l">接入率</div><div class="v">{{ind['接入率']}}%</div></div>
      <div class="stat" :class="ind['替代完成率']<80?'warn':'ok'"><div class="l">替代完成率</div><div class="v">{{ind['替代完成率']}}%</div></div>
      <div class="stat"><div class="l">双轨率</div><div class="v">{{ind['双轨率']}}%</div></div>
      <div class="stat" :class="ind['活跃率']<70?'warn':'ok'"><div class="l">活跃率(7日)</div><div class="v">{{ind['活跃率']}}%</div></div>
      <div class="stat" :class="ind['违规双系统数']>0?'danger':'ok'"><div class="l">违规双系统</div><div class="v">{{ind['违规双系统数']}}</div></div>
    </div>
    <div class="grid3">
      <div class="card"><h3>操作系统分布</h3><e-chart :option="charts.pie(ov.by_os)" /></div>
      <div class="card"><h3>CPU 分布</h3><e-chart :option="charts.pie(ov.by_cpu)" /></div>
      <div class="card"><h3>部门分布</h3><e-chart :option="charts.pie(ov.by_dept)" /></div>
    </div>
    <div class="grid2">
      <div class="card" v-if="act"><h3>近14日活跃终端</h3><e-chart :option="charts.line(act.series.map(s=>s.label),[{name:'活跃终端',data:act.series.map(s=>s.active),areaStyle:{opacity:.15}}])" /></div>
      <div class="card"><h3>负载 TOP10（在线）</h3><e-chart :option="charts.bar(ov.load_top.map(t=>t.hostname),[{name:'CPU%',data:ov.load_top.map(t=>t.cpu)},{name:'内存%',data:ov.load_top.map(t=>t.mem)},{name:'磁盘%',data:ov.load_top.map(t=>t.disk)}],{yAxis:{max:100}})" /></div>
    </div>
    <div class="grid2">
      <div class="card"><h3>客户端版本分布</h3><e-chart :option="charts.bar(ov.by_version.map(x=>x.name),[{name:'终端数',data:ov.by_version.map(x=>x.value)}])" /></div>
      <div class="card"><h3>品牌分布</h3><e-chart :option="charts.pie(ov.by_brand)" /></div>
    </div>
  </div>`,
};

Pages.terminals = {
  components: { EChart },
  setup() {
    const rows = ref([]); const total = ref(0); const options = ref({});
    const q = reactive({ page: 1, page_size: 20, keyword: '', dept: '', status: '', is_xinchuang: '', dual_system: '', is_cloud_desktop: '', os_name: '', cpu_model: '', brand: '' });
    const detail = ref(null); const drawer = ref(false);
    const load = async () => { const r = await api.get('/api/admin/terminals', q); rows.value = r.items; total.value = r.total; };
    const show = async (row) => { detail.value = await api.get('/api/admin/terminals/' + row.id); drawer.value = true; };
    const edit = async (row) => {
      const { value } = await ElMessageBox.prompt('使用人,部门（逗号分隔）', '编辑终端归属', { inputValue: (row.user_name || '') + ',' + (row.dept || '') });
      const [u, d] = value.split(/[,，]/); await api.put('/api/admin/terminals/' + row.id, { user_name: u, dept: d || '' }); load();
    };
    onMounted(async () => { options.value = await api.get('/api/admin/terminals/options'); load(); });
    return { rows, total, q, load, options, show, detail, drawer, edit, charts, boolOpts };
  },
  template: `<div class="card">
    <div class="toolbar">
      <el-input v-model="q.keyword" placeholder="主机名/使用人/IP/序列号" clearable @keyup.enter="load" />
      <el-select v-model="q.dept" placeholder="部门" clearable><el-option v-for="d in options.dept" :key="d" :value="d" :label="d"/></el-select>
      <el-select v-model="q.status" placeholder="状态" clearable><el-option value="online" label="在线"/><el-option value="offline" label="离线"/></el-select>
      <el-select v-model="q.is_xinchuang" placeholder="是否信创" clearable><el-option v-for="o in boolOpts" :key="o.value" v-bind="o"/></el-select>
      <el-select v-model="q.dual_system" placeholder="双系统" clearable><el-option v-for="o in boolOpts" :key="o.value" v-bind="o"/></el-select>
      <el-select v-model="q.is_cloud_desktop" placeholder="云桌面" clearable><el-option v-for="o in boolOpts" :key="o.value" v-bind="o"/></el-select>
      <el-select v-model="q.os_name" placeholder="操作系统" clearable filterable><el-option v-for="d in options.os_name" :key="d" :value="d" :label="d"/></el-select>
      <el-select v-model="q.cpu_model" placeholder="CPU" clearable filterable><el-option v-for="d in options.cpu_model" :key="d" :value="d" :label="d"/></el-select>
      <el-select v-model="q.brand" placeholder="品牌" clearable filterable><el-option v-for="d in options.brand" :key="d" :value="d" :label="d"/></el-select>
      <el-button type="primary" @click="q.page=1;load()">查询</el-button>
    </div>
    <el-table :data="rows" border stripe size="small">
      <el-table-column prop="hostname" label="主机名" min-width="110"/>
      <el-table-column prop="user_name" label="使用人" width="90"/>
      <el-table-column prop="dept" label="部门" width="100"/>
      <el-table-column prop="ip" label="IP" width="115"/>
      <el-table-column prop="cpu_model" label="CPU" min-width="140" show-overflow-tooltip/>
      <el-table-column prop="os_name" label="操作系统" min-width="110" show-overflow-tooltip/>
      <el-table-column label="内存/硬盘" width="110"><template #default="{row}">{{row.mem_total}}G / {{row.disk_total}}G</template></el-table-column>
      <el-table-column label="负载 CPU/内存/磁盘" width="150"><template #default="{row}">{{row.cpu_usage}}% / {{row.mem_usage}}% / {{row.disk_usage}}%</template></el-table-column>
      <el-table-column label="信创" width="70"><template #default="{row}"><el-tag size="small" :type="row.is_xinchuang?'success':'info'">{{row.is_xinchuang?'是':'否'}}</el-tag></template></el-table-column>
      <el-table-column label="双系统" width="70"><template #default="{row}"><el-tag size="small" :type="row.dual_system?'danger':'success'">{{row.dual_system?'违规':'正常'}}</el-tag></template></el-table-column>
      <el-table-column label="状态" width="70"><template #default="{row}"><el-tag size="small" :type="row.status==='online'?'success':'info'">{{row.status==='online'?'在线':'离线'}}</el-tag></template></el-table-column>
      <el-table-column prop="client_version" label="客户端" width="80"/>
      <el-table-column prop="last_seen" label="最后上报" width="150"/>
      <el-table-column label="操作" width="110" fixed="right"><template #default="{row}"><el-button link type="primary" @click="show(row)">详情</el-button><el-button link type="primary" @click="edit(row)">归属</el-button></template></el-table-column>
    </el-table>
    <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load" />
    <el-drawer v-model="drawer" size="60%" title="终端详情">
      <template v-if="detail">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item v-for="k in ['device_id','hostname','user_name','dept','ip','mac','os_name','os_version','arch','cpu_model','cpu_cores','mem_total','disk_total','disk_model','brand','model','serial','client_version','boot_time','first_seen','last_seen','cloud_server']" :key="k" :label="k">{{detail.terminal[k]}}</el-descriptions-item>
        </el-descriptions>
        <h4>负载趋势</h4>
        <e-chart height="220px" :option="charts.line(detail.loads.map(l=>l.created_at.slice(11,16)),[{name:'CPU',data:detail.loads.map(l=>l.cpu)},{name:'内存',data:detail.loads.map(l=>l.mem)},{name:'磁盘',data:detail.loads.map(l=>l.disk)}],{yAxis:{max:100}})" />
        <el-tabs>
          <el-tab-pane label="配件变更"><el-table :data="detail.changes" size="small"><el-table-column prop="component" label="配件"/><el-table-column prop="old_value" label="原值"/><el-table-column prop="new_value" label="新值"/><el-table-column prop="created_at" label="时间"/></el-table></el-tab-pane>
          <el-tab-pane label="预警"><el-table :data="detail.alerts" size="small"><el-table-column prop="rule_name" label="规则"/><el-table-column prop="level" label="级别" width="60"/><el-table-column prop="content" label="内容"/><el-table-column prop="created_at" label="时间"/></el-table></el-tab-pane>
          <el-tab-pane label="运行记录"><el-table :data="detail.records" size="small"><el-table-column prop="kind" label="类型" width="110"/><el-table-column label="内容"><template #default="{row}">{{JSON.stringify(row.content).slice(0,200)}}</template></el-table-column><el-table-column prop="created_at" label="时间" width="150"/></el-table></el-tab-pane>
          <el-tab-pane label="原始采集"><div class="mono">{{JSON.stringify(detail.terminal.hw_snapshot,null,2)}}</div></el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>
  </div>`,
};

Pages.cloud = {
  components: { CrudPage },
  setup() {
    const groups = ref([]); const kw = ref(''); const tab = ref('list');
    const load = async () => { groups.value = await api.get('/api/admin/cloud-desktops', { keyword: kw.value }); };
    onMounted(load);
    const cols = [{ prop: 'name', label: '服务端名称', required: true }, { prop: 'ip', label: 'IP' }, { prop: 'spec', label: '配置' }, { prop: 'location', label: '位置' }, { prop: 'remark', label: '备注' }];
    return { groups, kw, load, tab, cols };
  },
  template: `<el-tabs v-model="tab">
   <el-tab-pane label="云桌面资源清单" name="list">
    <div class="card"><div class="toolbar"><el-input v-model="kw" placeholder="用户端主机名/使用人/IP" clearable @keyup.enter="load"/><el-button type="primary" @click="load">查询</el-button></div>
    <div v-for="g in groups" :key="g.name" class="tree-group">
      <div class="hd"><div><b>{{g.name}}</b> <span class="muted">{{g.ip}} · {{g.spec}}</span></div><div><el-tag size="small">用户端 {{g.client_count}}</el-tag> <el-tag size="small" type="success">在线 {{g.online_count}}</el-tag></div></div>
      <el-table :data="g.clients" size="small" v-if="g.clients.length">
        <el-table-column prop="hostname" label="用户端主机"/><el-table-column prop="user_name" label="使用人"/><el-table-column prop="dept" label="部门"/><el-table-column prop="ip" label="IP"/><el-table-column prop="os_name" label="操作系统"/>
        <el-table-column label="状态" width="80"><template #default="{row}"><el-tag size="small" :type="row.status==='online'?'success':'info'">{{row.status==='online'?'在线':'离线'}}</el-tag></template></el-table-column>
        <el-table-column prop="last_seen" label="最后上报"/>
      </el-table>
      <div v-else class="muted" style="padding:12px">暂无用户端</div>
    </div></div>
   </el-tab-pane>
   <el-tab-pane label="云桌面服务端" name="servers"><crud-page api="/api/admin/cloud-servers" title="云桌面服务端" :columns="cols" /></el-tab-pane>
  </el-tabs>`,
};

Pages.hwchanges = {
  setup() {
    const rows = ref([]); const total = ref(0); const q = reactive({ page: 1, keyword: '', confirmed: '' });
    const load = async () => { const r = await api.get('/api/admin/hw-changes', q); rows.value = r.items; total.value = r.total; };
    const confirm = async (row) => { await api.post('/api/admin/hw-changes/' + row.id + '/confirm'); load(); };
    onMounted(load);
    return { rows, total, q, load, confirm };
  },
  template: `<div class="card"><div class="toolbar"><el-input v-model="q.keyword" placeholder="设备ID/配件" clearable/>
    <el-select v-model="q.confirmed" placeholder="确认状态" clearable><el-option value="false" label="未确认"/><el-option value="true" label="已确认"/></el-select><el-button type="primary" @click="load">查询</el-button></div>
    <el-table :data="rows" border size="small"><el-table-column prop="hostname" label="主机"/><el-table-column prop="user_name" label="使用人"/><el-table-column prop="component" label="配件"/>
      <el-table-column prop="old_value" label="原配件"/><el-table-column prop="new_value" label="新配件"/><el-table-column prop="created_at" label="发现时间" width="160"/>
      <el-table-column label="状态" width="90"><template #default="{row}"><el-tag size="small" :type="row.confirmed?'success':'warning'">{{row.confirmed?'已确认':'待确认'}}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="90"><template #default="{row}"><el-button v-if="!row.confirmed" link type="primary" @click="confirm(row)">确认更换</el-button></template></el-table-column></el-table>
    <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load"/></div>`,
};

Pages.indicators = {
  components: { EChart },
  setup() {
    const data = ref(null); const th = ref({}); const planned = ref({});
    const load = async () => {
      data.value = await api.get('/api/admin/indicators');
      th.value = (await api.get('/api/settings/indicator_thresholds')).value || {};
      planned.value = (await api.get('/api/settings/planned_terminals')).value || { _all: 0 };
    };
    const saveTh = async () => { await api.put('/api/settings/indicator_thresholds', { value: th.value }); await api.put('/api/settings/planned_terminals', { value: planned.value }); ElMessage.success('已保存'); load(); };
    onMounted(load);
    const KEYS = ['接入率', '替代完成率', '双轨率', '活跃率'];
    return { data, th, planned, saveTh, KEYS, charts };
  },
  template: `<div v-if="data">
    <div class="card"><h3>指标预警（标记异常/不合规指标）</h3>
      <el-alert v-for="w in data.overall['预警']" :key="w.indicator" :title="w.message + '（当前 ' + w.value + '，阈值 ' + w.threshold + '）'" type="error" show-icon :closable="false" style="margin-bottom:6px"/>
      <el-alert v-if="!data.overall['预警'].length" title="各项指标正常" type="success" show-icon :closable="false"/>
    </div>
    <div class="grid2">
      <div class="card"><h3>全局指标</h3><e-chart :option="charts.bar(KEYS,[{name:'%',data:KEYS.map(k=>({value:data.overall[k], itemStyle:{color: (k==='双轨率'? data.overall[k]>th[k] : data.overall[k]<th[k]) ? '#f56c6c':'#67c23a'}}))}],{yAxis:{max:100}})"/></div>
      <div class="card"><h3>各部门对比</h3><e-chart :option="charts.bar(data.by_dept.map(d=>d.dept), KEYS.map(k=>({name:k,data:data.by_dept.map(d=>d[k])})),{yAxis:{max:100}})"/></div>
    </div>
    <div class="card"><h3>部门指标明细</h3>
      <el-table :data="data.by_dept" border size="small">
        <el-table-column prop="dept" label="部门"/><el-table-column prop="终端总数" label="终端数"/><el-table-column prop="信创终端数" label="信创数"/>
        <el-table-column v-for="k in KEYS" :key="k" :label="k+'(%)'"><template #default="{row}"><span :style="{color:(k==='双轨率'? row[k]>th[k] : row[k]<th[k])?'#f56c6c':''}">{{row[k]}}</span></template></el-table-column>
        <el-table-column label="违规双系统"><template #default="{row}"><span :style="{color:row['违规双系统数']>0?'#f56c6c':''}">{{row['违规双系统数']}}</span></template></el-table-column>
      </el-table></div>
    <div class="card"><h3>异常/不合规终端</h3>
      <el-table :data="data.abnormal_terminals" border size="small" max-height="300"><el-table-column prop="hostname" label="主机"/><el-table-column prop="user_name" label="使用人"/><el-table-column prop="dept" label="部门"/><el-table-column prop="cpu_model" label="CPU"/><el-table-column prop="os_name" label="系统"/>
        <el-table-column label="问题"><template #default="{row}"><el-tag v-if="row.dual_system" type="danger" size="small">违规双系统</el-tag> <el-tag v-if="!row.is_xinchuang" type="warning" size="small">非信创</el-tag></template></el-table-column></el-table></div>
    <div class="card"><h3>指标阈值与应接入数配置</h3>
      <el-form inline><el-form-item v-for="(v,k) in th" :key="k" :label="k"><el-input-number v-model="th[k]" :min="0" :max="100000"/></el-form-item>
      <el-form-item label="应接入终端总数(0=按已接入计)"><el-input-number v-model="planned._all" :min="0"/></el-form-item>
      <el-button type="primary" @click="saveTh">保存</el-button></el-form></div>
  </div>`,
};

const METRICS = opts([['cpu_usage', 'CPU使用率(%)'], ['mem_usage', '内存使用率(%)'], ['disk_usage', '磁盘使用率(%)'], ['offline_days', '离线天数'], ['dual_system', '违规双系统'], ['hw_change', '配件更换'], ['usb', 'U盘使用'], ['blacklist_app', '违规软件(阈值填软件名,逗号分隔)'], ['non_xinchuang', '非信创终端']]);
Pages.alerts = {
  components: { CrudPage },
  setup() {
    const tab = ref('list'); const rows = ref([]); const total = ref(0); const sel = ref([]);
    const q = reactive({ page: 1, keyword: '', status: '未处理', level: '' });
    const load = async () => { const r = await api.get('/api/admin/alerts', q); rows.value = r.items; total.value = r.total; };
    const handle = async (ids) => { await api.post('/api/admin/alerts/handle', { ids }); ElMessage.success('已处理'); load(); };
    onMounted(load);
    const ruleCols = [{ prop: 'name', label: '规则名称', required: true }, { prop: 'metric', label: '监测项', type: 'select', options: METRICS },
      { prop: 'operator', label: '比较符', type: 'select', options: opts(['>', '>=', '<', '<=', '=', 'in']) }, { prop: 'threshold', label: '阈值' },
      { prop: 'level', label: '级别', type: 'select', options: opts(['高', '中', '低']) }, { prop: 'enabled', label: '启用', type: 'bool' }, { prop: 'description', label: '说明', list: false }];
    return { tab, rows, total, q, load, handle, sel, ruleCols };
  },
  template: `<el-tabs v-model="tab">
    <el-tab-pane label="预警信息" name="list"><div class="card">
      <div class="toolbar"><el-input v-model="q.keyword" placeholder="内容/设备" clearable/>
        <el-select v-model="q.status" placeholder="状态" clearable><el-option value="未处理" label="未处理"/><el-option value="已处理" label="已处理"/></el-select>
        <el-select v-model="q.level" placeholder="级别" clearable><el-option v-for="l in ['高','中','低']" :key="l" :value="l" :label="l"/></el-select>
        <el-button type="primary" @click="load">查询</el-button><el-button type="success" :disabled="!sel.length" @click="handle(sel.map(s=>s.id))">批量处理</el-button></div>
      <el-table :data="rows" border size="small" @selection-change="v=>sel=v"><el-table-column type="selection" width="40"/>
        <el-table-column prop="rule_name" label="规则" width="130"/><el-table-column label="级别" width="70"><template #default="{row}"><el-tag size="small" :type="row.level==='高'?'danger':row.level==='中'?'warning':'info'">{{row.level}}</el-tag></template></el-table-column>
        <el-table-column prop="content" label="预警内容" min-width="280" show-overflow-tooltip/><el-table-column prop="created_at" label="时间" width="160"/><el-table-column prop="status" label="状态" width="80"/>
        <el-table-column label="操作" width="80"><template #default="{row}"><el-button v-if="row.status==='未处理'" link type="primary" @click="handle([row.id])">处理</el-button></template></el-table-column></el-table>
      <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load"/></div></el-tab-pane>
    <el-tab-pane label="预警规则" name="rules"><crud-page api="/api/admin/alert-rules" title="预警规则" :columns="ruleCols"/></el-tab-pane>
  </el-tabs>`,
};

Pages.activity = {
  components: { EChart },
  setup() {
    const period = ref('day'); const data = ref(null);
    const load = async () => { data.value = await api.get('/api/admin/activity', { period: period.value, n: period.value === 'day' ? 30 : 12 }); };
    onMounted(load);
    return { period, data, load, charts };
  },
  template: `<div class="card"><div class="toolbar"><el-radio-group v-model="period" @change="load"><el-radio-button value="day">按日</el-radio-button><el-radio-button value="week">按周</el-radio-button></el-radio-group>
     <span class="muted" v-if="data">终端总数 {{data.total}}</span></div>
    <template v-if="data"><e-chart height="320px" :option="Object.assign(charts.bar(data.series.map(s=>s.label),[{name:'活跃终端数',data:data.series.map(s=>s.active)}]),{})"/>
    <e-chart height="260px" :option="charts.line(data.series.map(s=>s.label),[{name:'活跃率%',data:data.series.map(s=>s.rate),areaStyle:{opacity:.15}}],{yAxis:{max:100}})"/></template></div>`,
};

const KINDS = opts([['boot', '开机'], ['shutdown', '关机'], ['app_installed', '已安装应用'], ['app_usage', '应用使用'], ['usb', 'U盘使用'], ['printer', '打印机使用']]);
Pages.records = {
  components: { EChart },
  setup() {
    const rows = ref([]); const total = ref(0); const q = reactive({ page: 1, kind: '', device_id: '' }); const stats = ref(null);
    const load = async () => { const r = await api.get('/api/admin/run-records', q); rows.value = r.items; total.value = r.total; };
    onMounted(async () => { load(); stats.value = await api.get('/api/admin/run-records/stats'); });
    const kindLabel = (k) => (KINDS.find(o => o.value === k) || {}).label || k;
    const brief = (row) => { const c = row.content || {}; if (c.apps) return '应用：' + c.apps.slice(0, 15).join('、') + (c.apps.length > 15 ? ' 等' + c.apps.length + '个' : ''); return JSON.stringify(c).slice(0, 200); };
    return { rows, total, q, load, stats, KINDS, kindLabel, brief, charts };
  },
  template: `<div><div class="grid2" v-if="stats">
      <div class="card"><h3>近7日采集数据分布</h3><e-chart :option="charts.pie(stats.by_kind.map(x=>({name:kindLabel(x.name),value:x.value})))"/></div>
      <div class="card"><h3>应用使用 TOP15</h3><e-chart :option="charts.bar(stats.top_apps.map(x=>x.name),[{name:'次数',data:stats.top_apps.map(x=>x.value)}])"/></div></div>
    <div class="card"><div class="toolbar"><el-select v-model="q.kind" placeholder="数据类型" clearable><el-option v-for="o in KINDS" :key="o.value" v-bind="o"/></el-select>
      <el-input v-model="q.device_id" placeholder="设备ID" clearable/><el-button type="primary" @click="q.page=1;load()">查询</el-button></div>
    <el-table :data="rows" border size="small"><el-table-column prop="hostname" label="主机" width="120"/><el-table-column prop="user_name" label="使用人" width="90"/>
      <el-table-column label="类型" width="110"><template #default="{row}">{{kindLabel(row.kind)}}</template></el-table-column>
      <el-table-column label="内容" min-width="300" show-overflow-tooltip><template #default="{row}">{{brief(row)}}</template></el-table-column><el-table-column prop="created_at" label="时间" width="160"/></el-table>
    <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load"/></div></div>`,
};

function uploadAction(kind) {
  return { label: '上传安装包', click: (row, load) => {
    const inp = document.createElement('input'); inp.type = 'file';
    inp.onchange = async () => { const fd = new FormData(); fd.append('file', inp.files[0]); ElMessage.info('上传中…'); await api('/api/admin/upload/' + kind + '/' + row.id, { method: 'POST', body: fd }); ElMessage.success('上传成功'); load(); };
    inp.click();
  } };
}
Pages.versions = {
  components: { CrudPage },
  setup() {
    return { cols: [{ prop: 'version', label: '版本号', required: true, placeholder: '如 1.2.0' }, { prop: 'platform', label: '平台', type: 'select', options: opts([['linux', 'Linux(Ubuntu/麒麟/统信)'], ['windows', 'Windows']]) },
      { prop: 'arch', label: '架构', type: 'select', options: opts([['all', '全部'], ['x86_64', 'x86_64(海光/兆芯)'], ['aarch64', 'aarch64(飞腾/鲲鹏)']]) },
      { prop: 'status', label: '状态', type: 'select', options: opts(['草稿', '灰度', '已发布', '已下线']), tag: v => v === '已发布' ? 'success' : 'info' }, { prop: 'force_update', label: '强制更新', type: 'bool' },
      { prop: 'changelog', label: '变更说明', type: 'textarea', minWidth: 200 }, { prop: 'file_path', label: '安装包', form: false, formatter: v => v ? '已上传' : '未上传' }, { prop: 'created_at', label: '创建时间', form: false }],
      filters: [{ prop: 'platform', label: '平台', options: opts(['linux', 'windows']) }, { prop: 'status', label: '状态', options: opts(['草稿', '灰度', '已发布', '已下线']) }],
      actions: [uploadAction('version')] };
  },
  template: `<crud-page api="/api/admin/versions" title="版本" :columns="cols" :filters="filters" :row-actions="actions" :defaults="{platform:'linux',arch:'all',status:'草稿'}"/>`,
};
Pages.software = {
  components: { CrudPage },
  setup() {
    return { cols: [{ prop: 'name', label: '软件名称', required: true }, { prop: 'version', label: '版本' }, { prop: 'category', label: '分类', type: 'select', allowCreate: true, options: opts(['办公', '浏览器', '安全', '开发', '驱动', '工具']) },
      { prop: 'platform', label: '平台', type: 'select', options: opts(['linux', 'windows', 'all']) }, { prop: 'description', label: '说明', type: 'textarea' },
      { prop: 'size', label: '大小', form: false, formatter: fmtSize }, { prop: 'file_path', label: '安装包', form: false, formatter: v => v ? '已上传' : '未上传' }],
      actions: [uploadAction('software')] };
  },
  template: `<crud-page api="/api/admin/software" title="装机软件" :columns="cols" :row-actions="actions" :defaults="{platform:'linux',category:'办公'}"/>`,
};
Pages.dicts = {
  components: { CrudPage },
  setup() {
    const tools = [{ label: '按字典重新标准化终端数据', type: 'warning', click: async () => { const r = await api.post('/api/admin/dicts/apply'); ElMessage.success('已更新 ' + r.updated + ' 台终端'); } }];
    const T = opts([['cpu', 'CPU'], ['os', '操作系统'], ['brand', '品牌'], ['model', '型号'], ['disk', '硬盘']]);
    return { tools, T, cols: [{ prop: 'dict_type', label: '字典类型', type: 'select', options: T }, { prop: 'raw_value', label: '采集原始值(包含匹配)', required: true }, { prop: 'std_value', label: '规范名称', required: true }, { prop: 'extra', label: '属性', tip: 'CPU/OS 填“信创”或“非信创”参与信创判定' }, { prop: 'remark', label: '备注' }] };
  },
  template: `<crud-page api="/api/admin/dicts" title="字典项" :columns="cols" :filters="[{prop:'dict_type',label:'字典类型',options:T}]" :tool-actions="tools"/>`,
};
Pages.clientconfig = {
  components: { CrudPage },
  setup() {
    return { cols: [{ prop: 'key', label: '配置键', required: true }, { prop: 'name', label: '名称' }, { prop: 'value', label: '值/周期(秒)' },
      { prop: 'trigger', label: '执行方式', type: 'select', options: opts([['startup', '客户端启动时执行'], ['interval', '固定间隔执行'], ['manual', '参数']]) }, { prop: 'description', label: '说明' }] };
  },
  template: `<div><el-alert type="info" :closable="false" style="margin-bottom:12px" title="客户端每次上报时拉取以下配置，修改后自动下发，无需重启客户端。"/><crud-page api="/api/admin/client-config" title="客户端配置" :columns="cols"/></div>`,
};

/* ---------- 消息管理 ---------- */
Pages.messages = {
  setup() {
    const rows = ref([]); const total = ref(0); const q = reactive({ page: 1, keyword: '', status: '' });
    const templates = ref([]); const depts = ref([]);
    const dlg = reactive({ show: false, edit: null, form: {} });
    const rc = reactive({ show: false, rows: [] });
    const load = async () => { const r = await api.get('/api/admin/messages', q); rows.value = r.items; total.value = r.total; };
    const open = (row) => {
      dlg.edit = row; dlg.form = row ? { ...row } : { title: '', content: '', scope_type: 'all', scope_value: '', send_type: 'now', send_time: '', template_id: '' };
      dlg.show = true;
    };
    const useTpl = (id) => { const t = templates.value.find(x => x.id === id); if (t) { dlg.form.title = t.title || t.name; dlg.form.content = t.content; } };
    const save = async (draft) => {
      const f = { ...dlg.form, draft };
      if (dlg.edit) await api.put('/api/admin/messages/' + dlg.edit.id, Object.assign(f, { publish: !draft })); else await api.post('/api/admin/messages', f);
      ElMessage.success(draft ? '已存草稿' : (f.send_type === 'timed' ? '已加入定时发送队列' : '已发送')); dlg.show = false; load();
    };
    const del = async (row) => { await ElMessageBox.confirm('删除该消息？'); await api.del('/api/admin/messages/' + row.id); load(); };
    const sendNow = async (row) => { await api.post('/api/admin/messages/' + row.id + '/send'); ElMessage.success('已发送'); load(); };
    const receipts = async (row) => { rc.rows = await api.get('/api/admin/messages/' + row.id + '/receipts'); rc.show = true; };
    onMounted(async () => { load(); templates.value = (await api.get('/api/admin/message-templates', { page_size: 100 })).items; depts.value = (await api.get('/api/admin/terminals/options')).dept; });
    return { rows, total, q, load, dlg, open, save, del, sendNow, templates, useTpl, depts, rc, receipts };
  },
  template: `<div class="card"><div class="toolbar"><el-input v-model="q.keyword" placeholder="消息名称/内容" clearable/>
    <el-select v-model="q.status" placeholder="状态" clearable><el-option v-for="s in ['草稿','待发送','已发送']" :key="s" :value="s" :label="s"/></el-select>
    <el-button type="primary" @click="load">查询</el-button><el-button type="success" @click="open(null)">新建消息任务</el-button></div>
    <el-table :data="rows" border size="small"><el-table-column prop="title" label="消息名称" min-width="140"/>
      <el-table-column label="推送范围" width="150"><template #default="{row}">{{({all:'全部终端',dept:'部门',device:'指定终端'})[row.scope_type]}} {{row.scope_value}}</template></el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="155"/><el-table-column label="发送时间" width="155"><template #default="{row}">{{row.sent_at || (row.send_type==='timed' ? '定时 '+row.send_time : '')}}</template></el-table-column>
      <el-table-column prop="target_count" label="发送对象数" width="95"/><el-table-column prop="read_count" label="阅读对象数" width="95"/>
      <el-table-column label="状态" width="80"><template #default="{row}"><el-tag size="small" :type="row.status==='已发送'?'success':row.status==='待发送'?'warning':'info'">{{row.status}}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="230"><template #default="{row}"><el-button link type="primary" @click="open(row)">{{row.status==='已发送'?'查阅/编辑':'编辑'}}</el-button>
        <el-button v-if="row.status!=='已发送'" link type="success" @click="sendNow(row)">立即发送</el-button><el-button v-if="row.status==='已发送'" link @click="receipts(row)">阅读情况</el-button><el-button link type="danger" @click="del(row)">删除</el-button></template></el-table-column></el-table>
    <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load"/>
    <el-dialog v-model="dlg.show" :title="dlg.edit?'编辑消息':'新建消息任务'" width="640px">
      <el-form label-width="90px">
        <el-form-item label="消息模板" v-if="!dlg.edit"><el-select v-model="dlg.form.template_id" placeholder="选择模板后可二次编辑" clearable @change="useTpl" style="width:100%"><el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id"/></el-select></el-form-item>
        <el-form-item label="消息名称"><el-input v-model="dlg.form.title"/></el-form-item>
        <el-form-item label="消息内容"><el-input v-model="dlg.form.content" type="textarea" :rows="5"/></el-form-item>
        <template v-if="!dlg.edit || dlg.edit.status!=='已发送'">
        <el-form-item label="推送范围"><el-radio-group v-model="dlg.form.scope_type"><el-radio value="all">全部终端</el-radio><el-radio value="dept">按部门</el-radio><el-radio value="device">指定终端</el-radio></el-radio-group></el-form-item>
        <el-form-item v-if="dlg.form.scope_type==='dept'" label="部门"><el-select multiple style="width:100%" :model-value="(dlg.form.scope_value||'').split(',').filter(Boolean)" @update:model-value="v=>dlg.form.scope_value=v.join(',')"><el-option v-for="d in depts" :key="d" :value="d" :label="d"/></el-select></el-form-item>
        <el-form-item v-if="dlg.form.scope_type==='device'" label="终端"><el-input v-model="dlg.form.scope_value" placeholder="主机名或设备ID，逗号分隔"/></el-form-item>
        <el-form-item label="发送方式"><el-radio-group v-model="dlg.form.send_type"><el-radio value="now">即时发送</el-radio><el-radio value="timed">定时发送</el-radio></el-radio-group></el-form-item>
        <el-form-item v-if="dlg.form.send_type==='timed'" label="发送时间"><el-date-picker v-model="dlg.form.send_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss"/></el-form-item>
        </template>
      </el-form>
      <template #footer><el-button @click="dlg.show=false">取消</el-button><el-button v-if="!dlg.edit || dlg.edit.status==='草稿'" @click="save(true)">存草稿</el-button><el-button type="primary" @click="save(false)">{{dlg.edit && dlg.edit.status==='已发送' ? '保存' : (dlg.form.send_type==='timed'?'定时发送':'立即发送')}}</el-button></template>
    </el-dialog>
    <el-dialog v-model="rc.show" title="阅读情况" width="640px"><el-table :data="rc.rows" size="small" max-height="400"><el-table-column prop="hostname" label="主机"/><el-table-column prop="user_name" label="使用人"/><el-table-column prop="delivered_at" label="送达时间"/><el-table-column label="阅读时间"><template #default="{row}">{{row.read_at || '未读'}}</template></el-table-column></el-table></el-dialog>
  </div>`,
};
Pages.msgtemplates = {
  components: { CrudPage },
  setup() { return { cols: [{ prop: 'name', label: '模板名称', required: true }, { prop: 'title', label: '消息标题' }, { prop: 'content', label: '模板内容', type: 'textarea', rows: 5, minWidth: 260 }, { prop: 'created_at', label: '创建时间', form: false }] }; },
  template: `<crud-page api="/api/admin/message-templates" title="消息模板" :columns="cols"/>`,
};

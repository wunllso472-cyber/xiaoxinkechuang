/* 智能问答 / 模型管理 / 模型优化 / 知识库 / 合同智审 / 工具与插件 */

/* ---------------- 智能问答 ---------------- */
Pages.chat = {
  setup() {
    const sessions = ref([]); const sid = ref(''); const msgs = ref([]); const input = ref('');
    const models = ref([]); const modelId = ref(null); const mode = ref('chat'); const kbs = ref([]); const kbIds = ref([]);
    const busy = ref(false); let ctrl = null; const box = ref(null);
    const scroll = () => nextTick(() => { if (box.value) box.value.scrollTop = box.value.scrollHeight; });
    const loadSessions = async () => { sessions.value = await api.get('/api/chat/sessions'); };
    const openSession = async (s) => { const d = await api.get('/api/chat/sessions/' + s.id); sid.value = s.id; mode.value = d.mode; msgs.value = d.messages; scroll(); };
    const newSession = () => { sid.value = ''; msgs.value = []; };
    const send = () => {
      const text = input.value.trim(); if (!text || busy.value) return;
      msgs.value.push({ role: 'user', content: text }); input.value = '';
      const ans = reactive({ role: 'assistant', content: '', refs: [], model_name: '' }); msgs.value.push(ans); busy.value = true; scroll();
      ctrl = streamPost('/api/chat/send', { message: text, session_id: sid.value, model_id: modelId.value, mode: mode.value, kb_ids: kbIds.value.length ? kbIds.value : null }, (e) => {
        if (e.type === 'meta') { sid.value = e.session_id; ans.refs = e.refs; }
        else if (e.type === 'delta') { ans.content += e.text; scroll(); }
        else if (e.type === 'done') { ans.model_name = e.model; }
        else if (['end', 'error', 'aborted'].includes(e.type)) { busy.value = false; if (e.type === 'error') ans.content += '\n[' + e.text + ']'; loadSessions(); }
      });
    };
    const stop = async () => { if (sid.value) await api.post('/api/chat/stop/' + sid.value); setTimeout(() => ctrl && ctrl.abort(), 300); busy.value = false; };
    const del = async (s) => { await api.del('/api/chat/sessions/' + s.id); if (s.id === sid.value) newSession(); loadSessions(); };
    onMounted(async () => { loadSessions(); models.value = await api.get('/api/models/available'); kbs.value = await api.get('/api/kb/bases'); });
    return { sessions, sid, msgs, input, models, modelId, mode, kbs, kbIds, busy, send, stop, openSession, newSession, del, box };
  },
  template: `<div class="chat-wrap">
    <div class="chat-side"><el-button type="primary" style="width:100%;margin-bottom:8px" @click="newSession">+ 新会话</el-button>
      <div v-for="s in sessions" :key="s.id" class="s" :class="{active:s.id===sid}" @click="openSession(s)"><span>{{s.mode==='kb'?'[知识] ':''}}{{s.title}}</span><el-button link type="danger" size="small" style="float:right" @click.stop="del(s)">×</el-button></div></div>
    <div class="chat-main">
      <div class="toolbar" style="padding:10px 12px;margin:0;border-bottom:1px solid #ebeef5">
        <el-radio-group v-model="mode" size="small"><el-radio-button value="chat">智能问答</el-radio-button><el-radio-button value="kb">本地知识问答</el-radio-button></el-radio-group>
        <el-select v-model="modelId" placeholder="自动路由（默认模型+降级）" clearable size="small" style="width:220px"><el-option v-for="m in models" :key="m.id" :value="m.id" :label="m.name"/></el-select>
        <el-select v-if="mode==='kb'" v-model="kbIds" multiple placeholder="知识库（默认全部）" size="small" style="width:260px"><el-option v-for="k in kbs" :key="k.id" :value="k.id" :label="k.name"/></el-select>
        <span class="muted">会话ID：{{sid || '新会话'}}</span></div>
      <div class="chat-msgs" ref="box">
        <el-empty v-if="!msgs.length" description="试试：“我的电脑坏了需要报修”（多轮槽位填充） 或 切换到本地知识问答提问"/>
        <div v-for="(m,i) in msgs" :key="i" class="msg" :class="m.role"><div><div class="bubble">{{m.content || '…'}}</div>
          <div v-if="m.refs && m.refs.length" class="ref"><div v-for="(r,j) in m.refs" :key="j">[{{j+1}}] {{r.file}}（相关度 {{r.score}}）{{r.content.slice(0,60)}}…</div></div>
          <div class="meta" v-if="m.role==='assistant' && m.model_name">模型：{{m.model_name}}</div></div></div>
      </div>
      <div class="chat-input"><el-input v-model="input" type="textarea" :rows="2" placeholder="输入问题，Enter 发送，Shift+Enter 换行" @keydown.enter.exact.prevent="send"/>
        <el-button v-if="!busy" type="primary" @click="send">发送</el-button><el-button v-else type="danger" @click="stop">停止</el-button></div>
    </div></div>`,
};

Pages.sessions = {
  setup() {
    const rows = ref([]); const total = ref(0); const q = reactive({ page: 1, keyword: '' }); const cfg = ref({}); const detail = ref(null);
    const load = async () => { const r = await api.get('/api/admin/chat/sessions', q); rows.value = r.items; total.value = r.total; };
    const save = async () => { await api.put('/api/settings/chat', { value: cfg.value }); ElMessage.success('已保存，即时生效'); };
    const view = async (row) => { detail.value = await api.get('/api/chat/sessions/' + row.id).catch(() => null); if (!detail.value) ElMessage.info('仅可查看本人会话内容'); };
    onMounted(async () => { load(); cfg.value = (await api.get('/api/settings/chat')).value || {}; });
    return { rows, total, q, load, cfg, save, view, detail };
  },
  template: `<div><div class="card"><h3>多轮会话参数</h3><el-form inline>
      <el-form-item label="会话超时(分钟)"><el-input-number v-model="cfg.session_timeout_minutes" :min="5"/></el-form-item>
      <el-form-item label="上下文窗口(轮)"><el-input-number v-model="cfg.context_window_rounds" :min="0" :max="50"/></el-form-item>
      <el-form-item label="上下文策略"><el-select v-model="cfg.context_strategy" style="width:200px"><el-option value="window" label="滑动窗口"/><el-option value="summary" label="滑动窗口+历史摘要"/></el-select></el-form-item>
      <el-button type="primary" @click="save">保存</el-button></el-form></div>
    <div class="card"><h3>会话列表（Session 生命周期）</h3><div class="toolbar"><el-input v-model="q.keyword" placeholder="会话标题" clearable/><el-button type="primary" @click="load">查询</el-button></div>
    <el-table :data="rows" border size="small"><el-table-column prop="id" label="Session ID" width="280"/><el-table-column prop="title" label="标题"/><el-table-column prop="user" label="用户/设备" width="140"/>
      <el-table-column prop="mode" label="模式" width="70"/><el-table-column prop="intent" label="进行中意图" width="100"/><el-table-column label="状态" width="80"><template #default="{row}"><el-tag size="small" :type="row.expired?'info':'success'">{{row.expired?'已销毁':'活跃'}}</el-tag></template></el-table-column>
      <el-table-column prop="created_at" label="创建" width="155"/><el-table-column prop="last_active" label="最后活跃" width="155"/></el-table>
    <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load"/></div></div>`,
};

Pages.intents = {
  components: { CrudPage },
  setup() {
    return { cols: [{ prop: 'name', label: '意图名称', required: true }, { prop: 'keywords', label: '触发关键词', tip: '逗号分隔，命中即进入该意图的槽位填充' },
      { prop: 'description', label: '说明' }, { prop: 'action', label: '完成动作', type: 'select', options: opts([['none', '仅汇总'], ['create_ticket', '自动创建运维工单']]) },
      { prop: 'slots', label: '槽位定义', type: 'json', rows: 10, list: false, tip: '[{"name":"phone","label":"联系电话","required":true,"pattern":"(1[3-9]\\\\d{9})"}]' }, { prop: 'enabled', label: '启用', type: 'bool' }] };
  },
  template: `<div><el-alert type="info" :closable="false" style="margin-bottom:12px" title="状态跟踪（槽位填充）：对话命中意图后，系统持续跟踪必要参数（如时间、人数、偏好或报修信息），逐项追问直到收集完毕，再执行完成动作。"/>
    <crud-page api="/api/admin/intents" title="意图" :columns="cols" :defaults="{action:'none',enabled:true,slots:[]}"/></div>`,
};

/* ---------------- 模型管理 ---------------- */
const PROVIDERS = opts([['deepseek', 'DeepSeek'], ['qwen', '通义千问(Qwen)'], ['telechat', '星辰大模型(TeleChat)'], ['openai', 'OpenAI 兼容'], ['mock', '本地兜底(Mock)']]);
Pages.models = {
  components: { CrudPage },
  setup() {
    const route = ref({ strategy: 'priority', options: [] }); const crud = ref(null);
    const test = reactive({ show: false, id: null, prompt: '你好，请介绍一下你自己', res: null, loading: false });
    onMounted(async () => { route.value = await api.get('/api/admin/route'); });
    const saveRoute = async () => { await api.put('/api/admin/route', { strategy: route.value.strategy }); ElMessage.success('路由策略已生效'); };
    const cols = [{ prop: 'name', label: '名称', required: true }, { prop: 'provider', label: '厂商适配器', type: 'select', options: PROVIDERS },
      { prop: 'base_url', label: 'API 地址', list: false, placeholder: 'https://api.deepseek.com/v1' }, { prop: 'api_key', label: 'API Key', type: 'password', list: false },
      { prop: 'model', label: '模型标识', placeholder: 'deepseek-chat' }, { prop: 'temperature', label: 'temperature', type: 'number', step: 0.1, min: 0, max: 2, list: false },
      { prop: 'top_p', label: 'top_p', type: 'number', step: 0.05, min: 0, max: 1, list: false }, { prop: 'max_tokens', label: 'max_tokens', type: 'number', step: 256, list: false },
      { prop: 'timeout', label: '超时(秒)', type: 'number', list: false }, { prop: 'priority', label: '优先级', type: 'number', width: 70, tip: '数字越小越优先，失败按此顺序降级' },
      { prop: 'weight', label: '权重', type: 'number', width: 60 }, { prop: 'scene', label: '业务场景', placeholder: 'chat,kb,contract,ops', list: false },
      { prop: 'extra', label: '扩展参数(JSON)', type: 'json', list: false, tip: '透传给模型 API 的其他参数，如 {"frequency_penalty":0}' },
      { prop: 'version', label: '版本', width: 60 }, { prop: 'gray_percent', label: '灰度%', type: 'number', min: 0, max: 100, width: 70 },
      { prop: 'is_default', label: '默认', type: 'bool', width: 60 }, { prop: 'enabled', label: '启用', type: 'bool', width: 60 },
      { prop: 'health', label: '健康', form: false, width: 70, tag: v => v === '健康' ? 'success' : v === '异常' ? 'danger' : 'info' }];
    const health = async (row, load) => { const r = await api.post('/api/admin/models/' + row.id + '/health'); r.ok ? ElMessage.success('健康，' + r.latency_ms + 'ms') : ElMessage.error('异常：' + r.error); load(); };
    const publish = async (row, load) => {
      const { value } = await ElMessageBox.prompt('格式：版本号,灰度比例(0-100)。灰度100且勾选默认即全量发布', '版本/灰度发布', { inputValue: (row.version || 'v1') + ',' + (row.gray_percent ?? 100) });
      const [v, g] = value.split(/[,，]/); await api.post('/api/admin/models/' + row.id + '/publish', { version: v, gray_percent: +g, set_default: +g >= 100 }); load();
    };
    const runTest = async () => { test.loading = true; try { test.res = await api.post('/api/admin/models/' + test.id + '/test', { prompt: test.prompt }); } finally { test.loading = false; } };
    const actions = [{ label: '健康检查', click: health }, { label: '调用测试', click: (row) => { test.id = row.id; test.res = null; test.show = true; } }, { label: '发布', click: publish }];
    return { route, saveRoute, cols, actions, test, runTest, crud };
  },
  template: `<div>
    <div class="card"><h3>路由策略</h3><el-form inline><el-form-item label="策略"><el-select v-model="route.strategy" style="width:240px"><el-option v-for="o in route.options" :key="o.value" v-bind="o"/></el-select></el-form-item>
      <el-button type="primary" @click="saveRoute">保存（无需重启）</el-button></el-form>
      <div class="muted">统一模型调用接口屏蔽各厂商 API 差异；首选模型失败或无响应时自动降级到下一个启用的模型，本地兜底模型永远最后。用户可在客户端问答界面手动切换模型。</div></div>
    <crud-page ref="crud" api="/api/admin/models" title="模型" :columns="cols" :row-actions="actions" dialog-width="720px" :defaults="{provider:'deepseek',base_url:'https://api.deepseek.com/v1',model:'deepseek-chat',temperature:0.7,top_p:0.95,max_tokens:2048,timeout:60,priority:10,weight:1,gray_percent:100,version:'v1',enabled:true}"/>
    <el-dialog v-model="test.show" title="模型调用测试" width="600px"><el-input v-model="test.prompt" type="textarea"/><el-button type="primary" style="margin-top:8px" :loading="test.loading" @click="runTest">发送</el-button>
      <div v-if="test.res" class="ref" style="white-space:pre-wrap;margin-top:10px">{{test.res.ok ? '['+test.res.model+' · '+test.res.ms+'ms]\\n'+test.res.content : test.res.error}}</div></el-dialog>
  </div>`,
};

Pages.modelmetrics = {
  components: { EChart },
  setup() { const d = ref(null); onMounted(async () => { d.value = await api.get('/api/admin/models-metrics', { days: 7 }); }); return { d, charts }; },
  template: `<div v-if="d"><div class="grid2">
      <div class="card"><h3>近7日调用量与平均响应时间</h3><e-chart :option="Object.assign(charts.line(d.trend.map(t=>t.day),[{name:'调用量',data:d.trend.map(t=>t.calls)},{name:'平均耗时ms',data:d.trend.map(t=>t.avg_ms),yAxisIndex:1}]),{yAxis:[{type:'value'},{type:'value'}]})"/></div>
      <div class="card"><h3>各模型成功率(%)</h3><e-chart :option="charts.bar(d.models.map(m=>m.model),[{name:'成功率',data:d.models.map(m=>m.success_rate)}],{yAxis:{max:100}})"/></div></div>
    <div class="card"><h3>模型性能明细</h3><el-table :data="d.models" border size="small"><el-table-column prop="model" label="模型"/><el-table-column prop="calls" label="调用次数"/><el-table-column prop="avg_ms" label="平均响应(ms)"/><el-table-column prop="success_rate" label="成功率(%)"/><el-table-column prop="fallback" label="降级调用次数"/><el-table-column prop="tokens" label="输出Token"/></el-table></div>
    <div class="card"><h3>最近失败调用</h3><el-table :data="d.errors" size="small" border><el-table-column prop="model_name" label="模型" width="160"/><el-table-column prop="scene" label="场景" width="80"/><el-table-column prop="error" label="错误" show-overflow-tooltip/><el-table-column prop="created_at" label="时间" width="160"/></el-table></div></div>`,
};

Pages.finetune = {
  components: { EChart },
  setup() {
    const ds = ref([]); const jobs = ref([]); const job = ref(null); let timer = null;
    const up = reactive({ name: '', kind: '运维知识', file: null });
    const form = reactive({ dataset_id: null, name: '信创运维LoRA微调', base_model: 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B', method: 'lora', params: { lora_rank: 8, lora_alpha: 16, learning_rate: 0.0001, epochs: 3, batch_size: 4, cutoff_len: 2048 } });
    const load = async () => { ds.value = await api.get('/api/admin/ft/datasets'); jobs.value = await api.get('/api/admin/ft/jobs'); if (job.value) job.value = await api.get('/api/admin/ft/jobs/' + job.value.id); };
    const upload = async () => {
      if (!up.file) return ElMessage.warning('请选择文件');
      const fd = new FormData(); fd.append('name', up.name || up.file.name); fd.append('kind', up.kind); fd.append('file', up.file);
      await api('/api/admin/ft/datasets', { method: 'POST', body: fd }); ElMessage.success('已上传，后台预处理中'); setTimeout(load, 1500);
    };
    const create = async () => { await api.post('/api/admin/ft/jobs', form); ElMessage.success('训练任务已启动'); load(); };
    const view = async (j) => { job.value = await api.get('/api/admin/ft/jobs/' + j.id); };
    const stop = async (j) => { await api.post('/api/admin/ft/jobs/' + j.id + '/stop'); load(); };
    const retrain = async (j) => {
      const { value } = await ElMessageBox.prompt('修改超参数（JSON），基于该任务重新微调验证', '参数调整', { inputValue: JSON.stringify(j.params), inputType: 'textarea' });
      await api.post('/api/admin/ft/jobs/' + j.id + '/retrain', { params: JSON.parse(value) }); load();
    };
    onMounted(() => { load(); timer = setInterval(load, 3000); });
    onBeforeUnmount(() => clearInterval(timer));
    return { ds, jobs, job, up, form, upload, create, view, stop, retrain, charts };
  },
  template: `<div>
    <div class="grid2">
      <div class="card"><h3>① 微调数据集（2万+运维知识 / 1000+政策知识）</h3>
        <div class="toolbar"><el-input v-model="up.name" placeholder="数据集名称"/><el-select v-model="up.kind"><el-option value="运维知识" label="运维知识"/><el-option value="政策知识" label="政策知识"/></el-select>
          <input type="file" accept=".jsonl,.json,.csv,.xlsx" @change="e=>up.file=e.target.files[0]"/><el-button type="primary" @click="upload">上传并预处理</el-button></div>
        <div class="muted">支持 jsonl/json/csv/xlsx，字段 instruction/input/output 或 question/answer 或 问题/答案。预处理：格式标准化(alpaca)、去空/去重/乱码清洗、按技术栈/故障类型（政策按法规层级）分层分类。</div>
        <el-table :data="ds" size="small" border style="margin-top:8px"><el-table-column prop="name" label="名称"/><el-table-column prop="kind" label="类型" width="80"/><el-table-column prop="total" label="原始" width="60"/><el-table-column prop="valid" label="有效" width="60"/>
          <el-table-column label="分类" min-width="140"><template #default="{row}"><el-tag v-for="(v,k) in row.categories" :key="k" size="small" style="margin:1px">{{k}}:{{v}}</el-tag></template></el-table-column><el-table-column prop="status" label="状态" width="70"/></el-table></div>
      <div class="card"><h3>② 新建微调任务</h3><el-form label-width="100px" size="small">
        <el-form-item label="数据集"><el-select v-model="form.dataset_id"><el-option v-for="d in ds.filter(x=>x.status==='已处理')" :key="d.id" :value="d.id" :label="d.name+'（'+d.valid+'条）'"/></el-select></el-form-item>
        <el-form-item label="任务名"><el-input v-model="form.name"/></el-form-item><el-form-item label="基座模型"><el-input v-model="form.base_model"/></el-form-item>
        <el-form-item label="微调方法"><el-radio-group v-model="form.method"><el-radio value="lora">LoRA</el-radio><el-radio value="qlora">QLoRA(4bit)</el-radio></el-radio-group></el-form-item>
        <el-form-item label="超参数"><el-input-number v-model="form.params.lora_rank" :min="1"/> rank &nbsp;<el-input-number v-model="form.params.lora_alpha" :min="1"/> alpha</el-form-item>
        <el-form-item label=""><el-input-number v-model="form.params.learning_rate" :step="0.00005" :precision="5"/> lr &nbsp;<el-input-number v-model="form.params.epochs" :min="1"/> epochs</el-form-item>
        <el-form-item><el-button type="primary" @click="create" :disabled="!form.dataset_id">启动训练</el-button></el-form-item></el-form>
        <div class="muted">config.yaml 中配置 finetune.train_command（如 LLaMA-Factory）后在 GPU 服务器真实训练；未配置时以模拟方式演示训练监控流程。</div></div>
    </div>
    <div class="card"><h3>③ 训练任务与监控</h3><el-table :data="jobs" size="small" border><el-table-column prop="name" label="任务"/><el-table-column prop="method" label="方法" width="70"/><el-table-column label="参数"><template #default="{row}">{{JSON.stringify(row.params)}}</template></el-table-column>
      <el-table-column label="进度" width="160"><template #default="{row}"><el-progress :percentage="row.progress"/></template></el-table-column><el-table-column prop="status" label="状态" width="80"/><el-table-column prop="final_loss" label="最终Loss" width="90"/>
      <el-table-column label="操作" width="180"><template #default="{row}"><el-button link type="primary" @click="view(row)">监控</el-button><el-button v-if="row.status==='训练中'" link type="danger" @click="stop(row)">停止</el-button><el-button link @click="retrain(row)">调参重训</el-button></template></el-table-column></el-table>
      <template v-if="job"><h4>{{job.name}} · 损失函数变化</h4>
        <e-chart height="260px" :option="charts.line((job.metrics&&job.metrics.loss||[]).map(x=>x.step),[{name:'train loss',data:(job.metrics&&job.metrics.loss||[]).map(x=>x.loss)},{name:'eval loss',data:(job.metrics&&job.metrics.loss||[]).map(x=>{const e=(job.metrics.eval_loss||[]).find(y=>y.step===x.step);return e?e.loss:null}),connectNulls:true}])"/>
        <el-tabs><el-tab-pane label="训练日志"><div class="mono">{{job.log}}</div></el-tab-pane><el-tab-pane label="训练配置(LLaMA-Factory)"><div class="mono">{{JSON.stringify(job.train_config,null,2)}}</div></el-tab-pane></el-tabs></template></div>
  </div>`,
};

Pages.evaluate = {
  components: { CrudPage, EChart },
  setup() {
    const runs = ref([]); const sets = ref([]); const models = ref([]); const f = reactive({ eval_set_id: null, model_id: null, temperature: 0.3 }); const detail = ref(null); let timer;
    const load = async () => { runs.value = await api.get('/api/admin/eval-runs'); };
    const start = async () => { await api.post('/api/admin/eval-runs', { eval_set_id: f.eval_set_id, model_id: f.model_id, params: { temperature: f.temperature } }); ElMessage.success('评估已开始'); load(); };
    onMounted(async () => { load(); sets.value = (await api.get('/api/admin/eval-sets', { page_size: 100 })).items; models.value = await api.get('/api/models/available'); timer = setInterval(load, 4000); });
    onBeforeUnmount(() => clearInterval(timer));
    const cols = [{ prop: 'name', label: '测试集名称', required: true }, { prop: 'items', label: '测试题(JSON)', type: 'json', rows: 12, list: false, tip: '[{"question":"..","answer":"参考答案","keywords":["关键词"]}]' }, { prop: 'created_at', label: '创建时间', form: false }];
    return { runs, sets, models, f, start, detail, cols, charts, view: async (r) => { detail.value = await api.get('/api/admin/eval-runs/' + r.id); } };
  },
  template: `<div>
    <crud-page api="/api/admin/eval-sets" title="测试集" :columns="cols" :defaults="{items:[]}"/>
    <div class="card"><h3>模型评估（准确性 / 专业性 / 时效性）</h3>
      <div class="toolbar"><el-select v-model="f.eval_set_id" placeholder="测试集"><el-option v-for="s in sets" :key="s.id" :value="s.id" :label="s.name"/></el-select>
        <el-select v-model="f.model_id" placeholder="模型"><el-option v-for="m in models" :key="m.id" :value="m.id" :label="m.name"/></el-select>
        <span class="muted">temperature</span><el-input-number v-model="f.temperature" :step="0.1" :min="0" :max="2" size="small"/>
        <el-button type="primary" :disabled="!f.eval_set_id||!f.model_id" @click="start">开始评估</el-button></div>
      <e-chart v-if="runs.length" height="240px" :option="charts.bar(runs.slice(0,10).reverse().map(r=>'#'+r.id+' '+r.model_name),[{name:'准确率%',data:runs.slice(0,10).reverse().map(r=>r.accuracy)},{name:'专业性%',data:runs.slice(0,10).reverse().map(r=>r.professional)}],{yAxis:{max:100}})"/>
      <el-table :data="runs" size="small" border><el-table-column prop="id" label="#" width="50"/><el-table-column prop="model_name" label="模型"/><el-table-column label="参数"><template #default="{row}">{{JSON.stringify(row.params)}}</template></el-table-column>
        <el-table-column prop="accuracy" label="准确率%"/><el-table-column prop="professional" label="专业性%"/><el-table-column prop="avg_latency" label="平均耗时ms"/><el-table-column prop="status" label="状态"/><el-table-column prop="created_at" label="时间" width="155"/>
        <el-table-column label="" width="70"><template #default="{row}"><el-button link type="primary" @click="view(row)">明细</el-button></template></el-table-column></el-table></div>
    <el-dialog :model-value="!!detail" @update:model-value="detail=null" title="评估明细" width="900px"><el-table v-if="detail" :data="detail.results" size="small" max-height="500"><el-table-column prop="question" label="问题" width="180"/><el-table-column prop="answer" label="模型回答" show-overflow-tooltip/><el-table-column prop="reference" label="参考答案" width="160" show-overflow-tooltip/>
      <el-table-column prop="keyword_hit" label="关键词命中" width="90"/><el-table-column label="正确" width="60"><template #default="{row}">{{row.correct?'✓':'✗'}}</template></el-table-column><el-table-column prop="latency_ms" label="ms" width="70"/></el-table></el-dialog>
  </div>`,
};

/* ---------------- 信创知识库 ---------------- */
Pages.kb = {
  setup() {
    const kbs = ref([]); const cur = ref(null); const docs = ref([]); const total = ref(0); const q = reactive({ page: 1, keyword: '', history: 0 });
    const logs = reactive({ show: false, rows: [], title: '' }); const vers = reactive({ show: false, rows: [] }); const chunks = reactive({ show: false, rows: [] });
    const uploading = ref(false); let timer;
    const loadKbs = async () => { kbs.value = await api.get('/api/kb/bases'); if (!cur.value && kbs.value.length) pick(kbs.value[0]); };
    const pick = (k) => { cur.value = k; q.page = 1; loadDocs(); };
    const loadDocs = async () => { if (!cur.value) return; const r = await api.get('/api/kb/bases/' + cur.value.id + '/docs', q); docs.value = r.items; total.value = r.total; };
    const addKb = async () => { const { value } = await ElMessageBox.prompt('知识库名称', '新建知识库'); await api.post('/api/kb/bases', { name: value }); loadKbs(); };
    const delKb = async (k) => { await ElMessageBox.confirm('删除知识库及其全部文档？', '警告', { type: 'warning' }); await api.del('/api/kb/bases/' + k.id); cur.value = null; loadKbs(); };
    const upload = async (e) => {
      const fd = new FormData(); for (const f of e.target.files) fd.append('files', f);
      uploading.value = true;
      try { const r = await api('/api/kb/bases/' + cur.value.id + '/docs', { method: 'POST', body: fd }); r.forEach(x => (x.status.startsWith('冲突') ? ElMessage.warning : ElMessage.success)(x.filename + '：' + x.status)); } finally { uploading.value = false; e.target.value = ''; }
      loadDocs();
    };
    const showLogs = async (d) => { logs.rows = await api.get('/api/kb/docs/' + d.id + '/logs'); logs.title = d.filename; logs.show = true; };
    const showVers = async (d) => { vers.rows = await api.get('/api/kb/docs/' + d.id + '/versions'); vers.show = true; };
    const showChunks = async (d) => { chunks.rows = await api.get('/api/kb/docs/' + d.id + '/chunks'); chunks.show = true; };
    const rollback = async (d) => { await api.post('/api/kb/docs/' + d.id + '/rollback'); ElMessage.success('已回滚'); vers.show = false; loadDocs(); };
    const retry = async (d) => { await api.post('/api/kb/docs/' + d.id + '/retry'); loadDocs(); };
    const tags = async (d) => { const { value } = await ElMessageBox.prompt('标签（逗号分隔），保存即标记为人工校验', '分类标签校验', { inputValue: d.tags }); await api.put('/api/kb/docs/' + d.id + '/tags', { tags: value }); loadDocs(); };
    const del = async (d) => { await ElMessageBox.confirm('删除文档？'); await api.del('/api/kb/docs/' + d.id); loadDocs(); };
    onMounted(() => { loadKbs(); timer = setInterval(() => { if (docs.value.some(d => ['待处理', '处理中'].includes(d.status))) loadDocs(); }, 2000); });
    onBeforeUnmount(() => clearInterval(timer));
    return { kbs, cur, docs, total, q, pick, loadDocs, addKb, delKb, upload, uploading, logs, vers, chunks, showLogs, showVers, showChunks, rollback, retry, tags, del, fmtSize };
  },
  template: `<div style="display:flex;gap:16px">
    <div class="card" style="width:230px;flex-shrink:0"><h3>知识库 <el-button link type="primary" style="float:right" @click="addKb">+新建</el-button></h3>
      <div v-for="k in kbs" :key="k.id" @click="pick(k)" style="padding:8px;border-radius:6px;cursor:pointer" :style="{background: cur&&cur.id===k.id?'#eef3ff':''}">
        <div><b>{{k.name}}</b> <el-tag size="small" v-if="k.owner!=='public'" type="info">私有</el-tag></div><div class="muted">{{k.doc_count}} 文档 · {{k.chunk_count}} 分片</div></div></div>
    <div class="card" style="flex:1;min-width:0" v-if="cur"><h3>{{cur.name}} <el-button link type="danger" style="float:right" @click="delKb(cur)">删除知识库</el-button></h3>
      <div class="toolbar"><el-input v-model="q.keyword" placeholder="文件名/标签" clearable @keyup.enter="loadDocs"/><el-checkbox v-model="q.history" :true-value="1" :false-value="0" @change="loadDocs">含历史版本</el-checkbox><el-button type="primary" @click="loadDocs">查询</el-button>
        <label class="el-button el-button--success" :class="{'is-loading':uploading}">{{uploading?'上传中…':'批量导入文档'}}<input type="file" multiple hidden accept=".txt,.md,.pdf,.docx,.xlsx,.pptx,.ofd,.csv,.png,.jpg,.jpeg" @change="upload"/></label>
        <span class="muted">支持 Word/PDF/Excel/PPT/TXT/OFD，扫描件/图片走 OCR；同名文件自动生成新版本，重复内容冲突检测</span></div>
      <el-table :data="docs" border size="small"><el-table-column prop="filename" label="文件名" min-width="180" show-overflow-tooltip/><el-table-column prop="file_type" label="格式" width="60"/><el-table-column label="大小" width="80"><template #default="{row}">{{fmtSize(row.size)}}</template></el-table-column>
        <el-table-column label="版本" width="70"><template #default="{row}">v{{row.version}}<span v-if="!row.is_latest" class="muted">(历史)</span></template></el-table-column>
        <el-table-column label="标签" min-width="130"><template #default="{row}"><el-tag v-for="t in (row.tags||'').split(',').filter(Boolean)" :key="t" size="small" style="margin:1px">{{t}}</el-tag><span v-if="row.tag_checked" class="muted"> ✓已校验</span></template></el-table-column>
        <el-table-column label="处理进度" width="150"><template #default="{row}"><el-progress :percentage="row.progress" :status="row.status==='失败'?'exception':row.status==='完成'?'success':''"/></template></el-table-column>
        <el-table-column label="分片/过滤" width="85"><template #default="{row}">{{row.chunk_count}} / {{row.filtered_count}}</template></el-table-column>
        <el-table-column prop="created_at" label="导入时间" width="150"/>
        <el-table-column label="操作" width="250" fixed="right"><template #default="{row}"><el-button link type="primary" @click="showLogs(row)">日志</el-button><el-button link type="primary" @click="showChunks(row)">分片</el-button><el-button link @click="showVers(row)">版本</el-button><el-button link @click="tags(row)">标签</el-button>
          <el-button v-if="row.status==='失败'" link type="warning" @click="retry(row)">重试</el-button><el-button link type="danger" @click="del(row)">删除</el-button></template></el-table-column></el-table>
      <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="loadDocs"/></div>
    <el-dialog v-model="logs.show" :title="'导入日志 - '+logs.title" width="700px"><el-timeline><el-timeline-item v-for="l in logs.rows" :key="l.id" :timestamp="l.created_at" :type="l.level==='ERROR'?'danger':'primary'">{{l.message}}</el-timeline-item></el-timeline></el-dialog>
    <el-dialog v-model="vers.show" title="历史版本追溯" width="700px"><el-table :data="vers.rows" size="small"><el-table-column label="版本" width="70"><template #default="{row}">v{{row.version}}</template></el-table-column><el-table-column prop="md5" label="MD5"/><el-table-column prop="created_at" label="导入时间"/><el-table-column label="当前" width="60"><template #default="{row}">{{row.is_latest?'✓':''}}</template></el-table-column>
      <el-table-column width="80"><template #default="{row}"><el-button v-if="!row.is_latest" link type="primary" @click="rollback(row)">恢复</el-button></template></el-table-column></el-table></el-dialog>
    <el-dialog v-model="chunks.show" title="文本分片（预处理结果）" width="800px"><div v-for="c in chunks.rows" :key="c.seq" class="ref"><b>#{{c.seq}}</b> {{c.content}}</div></el-dialog>
  </div>`,
};

Pages.kbsearch = {
  setup() {
    const kbs = ref([]); const f = reactive({ kb_ids: [], query: '', mode: '', top_k: null, threshold: null }); const res = ref(null); const cfg = ref({});
    const ev = reactive({ text: '打印机无法打印|CUPS\n查看系统版本|nkvers', res: null });
    const search = async () => { res.value = await api.post('/api/kb/search', f); };
    const save = async () => { await api.put('/api/kb/settings', cfg.value); ElMessage.success('检索参数已更新，即时生效'); };
    const evaluate = async () => {
      const cases = ev.text.split('\n').filter(Boolean).map(l => { const [query, expected] = l.split('|'); return { query, expected }; });
      ev.res = await api.post('/api/kb/evaluate', { kb_ids: f.kb_ids.length ? f.kb_ids : kbs.value.map(k => k.id), cases, mode: f.mode || null });
    };
    onMounted(async () => { kbs.value = await api.get('/api/kb/bases'); f.kb_ids = kbs.value.map(k => k.id); cfg.value = await api.get('/api/kb/settings'); });
    return { kbs, f, res, search, cfg, save, ev, evaluate };
  },
  template: `<div><div class="card"><h3>检索策略参数（相似度阈值动态调整）</h3><el-form inline size="small">
      <el-form-item label="检索模式"><el-select v-model="cfg.search_mode" style="width:150px"><el-option value="vector" label="语义检索"/><el-option value="keyword" label="关键词检索"/><el-option value="hybrid" label="混合检索"/></el-select></el-form-item>
      <el-form-item label="TopK"><el-input-number v-model="cfg.top_k" :min="1" :max="20"/></el-form-item><el-form-item label="相似度阈值"><el-input-number v-model="cfg.score_threshold" :step="0.01" :min="0" :max="1"/></el-form-item>
      <el-form-item label="混合权重(向量)"><el-input-number v-model="cfg.hybrid_alpha" :step="0.1" :min="0" :max="1"/></el-form-item>
      <el-form-item label="分片大小"><el-input-number v-model="cfg.chunk_size" :step="50"/></el-form-item><el-form-item label="重叠"><el-input-number v-model="cfg.chunk_overlap" :step="10"/></el-form-item>
      <el-button type="primary" @click="save">保存</el-button></el-form></div>
    <div class="grid2"><div class="card"><h3>检索测试</h3>
      <div class="toolbar"><el-select v-model="f.kb_ids" multiple placeholder="知识库" style="width:240px"><el-option v-for="k in kbs" :key="k.id" :value="k.id" :label="k.name"/></el-select>
        <el-select v-model="f.mode" placeholder="模式(默认)" clearable style="width:130px"><el-option value="vector" label="语义"/><el-option value="keyword" label="关键词"/><el-option value="hybrid" label="混合"/></el-select></div>
      <div class="toolbar"><el-input v-model="f.query" placeholder="输入查询" @keyup.enter="search" style="width:360px"/><el-button type="primary" @click="search">检索</el-button></div>
      <div v-if="res"><div class="muted">耗时 {{res.ms}}ms，命中 {{res.hits.length}} 条（已去重合并、重排序）</div>
        <div v-for="(h,i) in res.hits" :key="h.id" class="ref"><b>#{{i+1}} {{h.filename}}</b> 综合 {{h.score}} · 向量 {{h.vector_score}} · 关键词 {{h.keyword_score}} · 重排 {{h.rerank_score}}<div>{{h.content}}</div></div></div></div>
      <div class="card"><h3>检索质量评估（召回率 / 精确率）</h3><div class="muted">每行：查询|期望命中的文件名或关键词</div>
        <el-input v-model="ev.text" type="textarea" :rows="6"/><el-button type="primary" style="margin-top:8px" @click="evaluate">评估</el-button>
        <div v-if="ev.res" style="margin-top:10px"><el-tag size="large">召回率 {{ev.res.recall}}%</el-tag> <el-tag size="large" type="success">精确率 {{ev.res.precision}}%</el-tag>
          <el-table :data="ev.res.details" size="small"><el-table-column prop="query" label="查询"/><el-table-column prop="hits" label="命中"/><el-table-column prop="relevant" label="相关"/></el-table></div></div></div></div>`,
};

Pages.ragmetrics = {
  components: { EChart },
  setup() { const d = ref(null); onMounted(async () => { d.value = await api.get('/api/kb/metrics'); }); return { d, charts }; },
  template: `<div v-if="d"><div class="stat-row"><div class="stat"><div class="l">近7日检索次数</div><div class="v">{{d.count}}</div></div><div class="stat"><div class="l">平均检索耗时</div><div class="v">{{d.avg_ms}}ms</div></div>
      <div class="stat"><div class="l">平均最高相似度</div><div class="v">{{d.avg_top_score}}</div></div><div class="stat"><div class="l">平均命中数</div><div class="v">{{d.avg_hits}}</div></div>
      <div class="stat warn"><div class="l">零命中率</div><div class="v">{{d.zero_hit_rate}}%</div></div><div class="stat ok"><div class="l">用户满意度</div><div class="v">{{d.satisfaction==null?'-':d.satisfaction+'%'}}</div></div></div>
    <div class="grid2"><div class="card"><h3>检索量与耗时</h3><e-chart :option="Object.assign(charts.bar(d.trend.map(t=>t.day),[{name:'检索次数',data:d.trend.map(t=>t.count)},{name:'平均耗时ms',type:'line',yAxisIndex:1,data:d.trend.map(t=>t.avg_ms)}]),{yAxis:[{type:'value'},{type:'value'}]})"/></div>
      <div class="card"><h3>检索相关度趋势</h3><e-chart :option="charts.line(d.trend.map(t=>t.day),[{name:'平均最高相似度',data:d.trend.map(t=>t.avg_score)}])"/></div></div>
    <div class="card"><h3>最近检索链路 <span class="muted">（向量模型：{{d.embedding}}）</span></h3><el-table :data="d.recent" size="small" border><el-table-column prop="query" label="查询" show-overflow-tooltip/><el-table-column prop="mode" label="模式" width="80"/><el-table-column prop="hit_count" label="命中" width="60"/><el-table-column prop="top_score" label="最高分" width="80"/><el-table-column prop="retrieve_ms" label="检索ms" width="80"/><el-table-column prop="created_at" label="时间" width="160"/></el-table></div></div>`,
};

/* ---------------- 合同智审 ---------------- */
const riskType = (r) => ({ 高: 'danger', 中: 'warning', 低: 'info', 无: 'success' })[r] || 'info';
Pages.contracts = {
  setup() {
    const rows = ref([]); const total = ref(0); const q = reactive({ page: 1, keyword: '', risk_level: '' }); const tpls = ref([]);
    const up = reactive({ template_id: null, use_llm: false }); const cur = ref(null); const drawer = ref(false); let timer;
    const load = async () => { const r = await api.get('/api/contract', q); rows.value = r.items; total.value = r.total; };
    const upload = async (e) => {
      const fd = new FormData(); fd.append('file', e.target.files[0]); fd.append('template_id', up.template_id || 0); fd.append('use_llm', up.use_llm ? 1 : 0);
      await api('/api/contract/upload', { method: 'POST', body: fd }); e.target.value = ''; ElMessage.success('已上传，正在解析审查'); load();
    };
    const open = async (row) => { cur.value = await api.get('/api/contract/' + row.id); drawer.value = true; };
    const fp = async (it) => { await api.post('/api/contract/' + cur.value.id + '/false-positive', { rule_id: it.rule_id }); it.false_positive = true; ElMessage.success('已标记误报'); };
    const reanalyze = async () => { await api.post('/api/contract/' + cur.value.id + '/reanalyze', { use_llm: up.use_llm, template_id: up.template_id }); drawer.value = false; ElMessage.success('已重新审查'); setTimeout(load, 1500); };
    onMounted(async () => { load(); tpls.value = (await api.get('/api/contract/templates', { page_size: 100 })).items; timer = setInterval(() => { if (rows.value.some(r => ['待审查', '解析中'].includes(r.status))) load(); }, 2000); });
    onBeforeUnmount(() => clearInterval(timer));
    return { rows, total, q, load, tpls, up, upload, open, cur, drawer, fp, reanalyze, riskType };
  },
  template: `<div class="card">
    <div class="toolbar"><el-select v-model="up.template_id" placeholder="比对模板(默认第一个)" clearable style="width:220px"><el-option v-for="t in tpls" :key="t.id" :value="t.id" :label="t.name"/></el-select>
      <el-checkbox v-model="up.use_llm">启用大模型增强（要素补全+LLM规则）</el-checkbox>
      <label class="el-button el-button--primary">上传合同（PDF/OFD/Word…）<input type="file" hidden accept=".pdf,.ofd,.docx,.xlsx,.pptx,.txt,.png,.jpg" @change="upload"/></label>
      <el-input v-model="q.keyword" placeholder="文件名" clearable @keyup.enter="load"/><el-select v-model="q.risk_level" placeholder="风险等级" clearable><el-option v-for="r in ['高','中','低','无']" :key="r" :value="r" :label="r"/></el-select><el-button @click="load">查询</el-button></div>
    <el-table :data="rows" border size="small"><el-table-column prop="filename" label="合同文件" min-width="200"/><el-table-column prop="file_type" label="格式" width="60"/><el-table-column prop="uploader" label="上传人" width="100"/>
      <el-table-column prop="status" label="状态" width="80"/><el-table-column label="风险" width="70"><template #default="{row}"><el-tag v-if="row.risk_level" size="small" :type="riskType(row.risk_level)">{{row.risk_level}}</el-tag></template></el-table-column>
      <el-table-column prop="failed" label="不合规项" width="80"/><el-table-column prop="duration_ms" label="耗时ms" width="80"/><el-table-column prop="created_at" label="上传时间" width="155"/>
      <el-table-column label="操作" width="80"><template #default="{row}"><el-button link type="primary" @click="open(row)">审查结果</el-button></template></el-table-column></el-table>
    <el-pagination style="margin-top:12px" background layout="total, prev, pager, next" :total="total" v-model:current-page="q.page" @current-change="load"/>
    <el-drawer v-model="drawer" size="70%" :title="cur && cur.filename">
      <template v-if="cur && cur.review">
        <el-alert v-if="cur.review.error" :title="'解析失败：'+cur.review.error" type="error"/>
        <template v-else>
        <div style="margin-bottom:12px">综合风险：<el-tag :type="riskType(cur.risk_level)" size="large">{{cur.risk_level}}</el-tag>
          <span class="muted"> 共 {{cur.review.total}} 条规则，不合规 {{cur.review.failed}} 条</span> <el-button size="small" @click="reanalyze">重新审查</el-button> <a :href="'/api/contract/'+cur.id+'/file'" target="_blank">下载原文</a></div>
        <el-tabs>
          <el-tab-pane label="合规性研判">
            <el-table :data="cur.review.items.slice().sort((a,b)=>a.passed-b.passed)" size="small" border :row-style="({row})=>row.passed?{}:{background:'#fef0f0'}">
              <el-table-column prop="code" label="编号" width="70"/><el-table-column prop="name" label="审查规则" width="180"/><el-table-column prop="category" label="类别" width="100"/>
              <el-table-column label="级别" width="60"><template #default="{row}"><el-tag size="small" :type="riskType(row.level)">{{row.level}}</el-tag></template></el-table-column>
              <el-table-column label="结果" width="80"><template #default="{row}"><el-tag size="small" :type="row.passed?'success':'danger'">{{row.passed?'合规':'不合规'}}</el-tag></template></el-table-column>
              <el-table-column prop="message" label="预警提醒" show-overflow-tooltip/>
              <el-table-column width="80"><template #default="{row}"><el-button v-if="!row.passed && !row.false_positive" link size="small" @click="fp(row)">误报</el-button><span v-if="row.false_positive" class="muted">已标误报</span></template></el-table-column></el-table></el-tab-pane>
          <el-tab-pane label="要素提取"><el-descriptions :column="2" border size="small"><el-descriptions-item v-for="(v,k) in cur.elements.elements" :key="k" :label="k"><span :class="v?'':'diff-red'">{{v || '未识别'}}</span></el-descriptions-item></el-descriptions>
            <h4>实体识别</h4><div v-for="(v,k) in cur.elements.entities" :key="k" style="margin-bottom:6px"><b>{{k}}：</b><el-tag v-for="x in v" :key="x" size="small" style="margin:2px">{{x}}</el-tag></div></el-tab-pane>
          <el-tab-pane label="模板差异" v-if="cur.diff"><div class="muted" style="margin-bottom:8px">比对模板：{{cur.diff.template}}</div>
            <el-table :data="cur.diff.items" size="small" border><el-table-column prop="clause" label="模板条款"/><el-table-column label="必选" width="60"><template #default="{row}">{{row.required?'是':'否'}}</template></el-table-column>
              <el-table-column label="比对结果"><template #default="{row}"><b :class="'diff-'+row.color">● {{row.status}}</b></template></el-table-column><el-table-column prop="matched_title" label="合同对应条款"/><el-table-column label="命中关键词"><template #default="{row}">{{row.keywords_hit.join('、')}}</template></el-table-column></el-table></el-tab-pane>
          <el-tab-pane label="条款结构"><el-collapse><el-collapse-item v-for="(c,i) in cur.structure.clauses" :key="i" :title="(c.level===2?'　':'')+c.title"><div style="white-space:pre-wrap">{{c.content}}</div></el-collapse-item></el-collapse>
            <div v-if="cur.structure.tables.length"><h4>识别表格</h4><el-table v-for="(t,i) in cur.structure.tables" :key="i" :data="t.slice(1)" size="small" border style="margin-bottom:8px"><el-table-column v-for="(h,j) in t[0]" :key="j" :label="h"><template #default="{row}">{{row[j]}}</template></el-table-column></el-table></div></el-tab-pane>
          <el-tab-pane label="原文"><div style="white-space:pre-wrap;font-size:13px">{{cur.text}}</div></el-tab-pane>
        </el-tabs></template>
      </template><el-empty v-else description="审查中…"/>
    </el-drawer></div>`,
};

const RULE_TYPES = opts([['element_required', '要素必须存在'], ['keyword_required', '必须包含关键词'], ['keyword_forbidden', '禁止出现关键词'], ['regex_required', '必须匹配正则'], ['regex_forbidden', '禁止匹配正则'], ['amount_max', '金额上限阈值'], ['amount_consistent', '大小写金额一致'], ['llm', '大模型研判']]);
const RULE_TPL = { element_required: { element: '甲方' }, keyword_required: { keywords: ['违约'], any: true }, keyword_forbidden: { keywords: ['无限连带'] }, regex_required: { pattern: '', message: '' }, regex_forbidden: { pattern: '' }, amount_max: { pattern: '单价[^\\n\\d]{0,10}([\\d,]+(?:\\.\\d+)?)\\s*元', max: 10000 }, amount_consistent: {}, llm: { prompt: '请判断该合同是否...' } };
Pages.rules = {
  setup() {
    const rows = ref([]); const total = ref(0); const q = reactive({ page: 1, page_size: 50, keyword: '', category: '' });
    const ed = reactive({ show: false, form: {}, params: '', testText: '', testRes: null });
    const load = async () => { const r = await api.get('/api/contract/rules', q); rows.value = r.items; total.value = r.total; };
    const open = (row) => { ed.form = row ? { ...row } : { code: 'R' + String(total.value + 1).padStart(3, '0'), name: '', category: '条款完整性', rule_type: 'keyword_required', level: '中', enabled: true, description: '' }; ed.params = JSON.stringify(row ? row.params : RULE_TPL.keyword_required, null, 2); ed.testRes = null; ed.show = true; };
    const typeChange = (t) => { ed.params = JSON.stringify(RULE_TPL[t], null, 2); };
    const save = async () => { const d = { ...ed.form, params: JSON.parse(ed.params || '{}') }; if (d.id) { d.version = (d.version || 1) + 1; await api.put('/api/contract/rules/' + d.id, d); } else await api.post('/api/contract/rules', d); ed.show = false; load(); };
    const test = async () => { ed.testRes = await api.post('/api/contract-rules/test', { rule_type: ed.form.rule_type, params: JSON.parse(ed.params || '{}'), text: ed.testText }); };
    const toggle = async (row) => { await api.put('/api/contract/rules/' + row.id, { enabled: row.enabled }); };
    const del = async (row) => { await ElMessageBox.confirm('删除规则？'); await api.del('/api/contract/rules/' + row.id); load(); };
    const exp = async () => { const d = await api.get('/api/contract-rules/export'); const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' })); a.download = 'review_rules.json'; a.click(); };
    const imp = (e) => { const r = new FileReader(); r.onload = async () => { const res = await api.post('/api/contract-rules/import', { rules: JSON.parse(r.result) }); ElMessage.success('导入 ' + res.imported + ' 条'); load(); }; r.readAsText(e.target.files[0]); };
    const copy = (row) => { open(row); ed.form = { ...row, id: undefined, code: row.code + '-C', name: row.name + '(复制)', version: 1 }; };
    onMounted(load);
    return { rows, total, q, load, ed, open, typeChange, save, test, toggle, del, exp, imp, copy, RULE_TYPES, riskType };
  },
  template: `<div class="card"><div class="toolbar"><el-input v-model="q.keyword" placeholder="规则名称/编号" clearable/><el-select v-model="q.category" placeholder="类别" clearable><el-option v-for="c in ['要素完整性','条款完整性','金额审查','签章审查','信创合规','风险条款','付款审查','文本规范']" :key="c" :value="c" :label="c"/></el-select>
      <el-button type="primary" @click="load">查询</el-button><el-button type="success" @click="open(null)">新增规则</el-button><el-button @click="exp">批量导出</el-button><label class="el-button">批量导入<input type="file" hidden accept=".json" @change="imp"/></label><span class="muted">共 {{total}} 条规则</span></div>
    <el-table :data="rows" border size="small"><el-table-column prop="code" label="编号" width="80"/><el-table-column prop="name" label="规则名称" min-width="160"/><el-table-column prop="category" label="类别" width="100"/>
      <el-table-column label="类型" width="130"><template #default="{row}">{{(RULE_TYPES.find(o=>o.value===row.rule_type)||{}).label}}</template></el-table-column>
      <el-table-column label="参数" min-width="200" show-overflow-tooltip><template #default="{row}">{{JSON.stringify(row.params)}}</template></el-table-column>
      <el-table-column label="级别" width="60"><template #default="{row}"><el-tag size="small" :type="riskType(row.level)">{{row.level}}</el-tag></template></el-table-column><el-table-column label="版本" width="55"><template #default="{row}">v{{row.version}}</template></el-table-column>
      <el-table-column label="启用" width="65"><template #default="{row}"><el-switch v-model="row.enabled" size="small" @change="toggle(row)"/></template></el-table-column>
      <el-table-column label="操作" width="150"><template #default="{row}"><el-button link type="primary" @click="open(row)">编辑</el-button><el-button link @click="copy(row)">复用</el-button><el-button link type="danger" @click="del(row)">删除</el-button></template></el-table-column></el-table>
    <el-dialog v-model="ed.show" title="规则可视化编辑器" width="760px"><el-form label-width="90px" size="small">
      <el-form-item label="编号/名称"><el-input v-model="ed.form.code" style="width:100px"/>&nbsp;<el-input v-model="ed.form.name" style="width:400px"/></el-form-item>
      <el-form-item label="类别/级别"><el-select v-model="ed.form.category" allow-create filterable style="width:160px"><el-option v-for="c in ['要素完整性','条款完整性','金额审查','签章审查','信创合规','风险条款','付款审查','文本规范']" :key="c" :value="c" :label="c"/></el-select>&nbsp;<el-radio-group v-model="ed.form.level"><el-radio-button value="高">高</el-radio-button><el-radio-button value="中">中</el-radio-button><el-radio-button value="低">低</el-radio-button></el-radio-group></el-form-item>
      <el-form-item label="规则类型"><el-radio-group v-model="ed.form.rule_type" @change="typeChange"><el-radio-button v-for="t in RULE_TYPES" :key="t.value" :value="t.value">{{t.label}}</el-radio-button></el-radio-group></el-form-item>
      <el-form-item label="规则参数"><el-input v-model="ed.params" type="textarea" :rows="5" style="font-family:monospace"/></el-form-item>
      <el-form-item label="说明"><el-input v-model="ed.form.description"/></el-form-item>
      <el-form-item label="即时测试"><el-input v-model="ed.testText" type="textarea" :rows="3" placeholder="粘贴一段合同文本测试规则"/><el-button style="margin-top:6px" @click="test">测试</el-button>
        <el-tag v-if="ed.testRes" :type="ed.testRes.passed?'success':'danger'" style="margin-left:8px">{{ed.testRes.passed?'合规':'不合规：'+ed.testRes.message}}</el-tag></el-form-item></el-form>
      <template #footer><el-button @click="ed.show=false">取消</el-button><el-button type="primary" @click="save">保存（版本+1）</el-button></template></el-dialog></div>`,
};

Pages.ctemplates = {
  components: { CrudPage },
  setup() { return { cols: [{ prop: 'name', label: '模板名称', required: true }, { prop: 'category', label: '合同类别' }, { prop: 'industry', label: '行业' }, { prop: 'clauses', label: '条款要素定义', type: 'json', rows: 14, list: false, tip: '[{"name":"违约责任","required":true,"keywords":["违约"],"standard_text":"可选：标准条款文本，用于内容冲突检测"}]' }, { prop: 'content', label: '模板全文(可选)', type: 'textarea', list: false }, { prop: 'created_at', label: '创建时间', form: false }] }; },
  template: `<crud-page api="/api/contract/templates" title="合同模板" :columns="cols" dialog-width="760px" :defaults="{category:'采购合同',industry:'通用',clauses:[]}"/>`,
};

Pages.rulestats = {
  components: { EChart },
  setup() { const d = ref(null); onMounted(async () => { d.value = await api.get('/api/contract/stats'); }); return { d, charts }; },
  template: `<div v-if="d"><div class="stat-row"><div class="stat"><div class="l">已审查合同</div><div class="v">{{d.contracts}}</div></div><div class="stat"><div class="l">平均审查耗时</div><div class="v">{{d.avg_ms}}ms</div></div>
      <div class="stat danger"><div class="l">高风险</div><div class="v">{{d.risk['高']||0}}</div></div><div class="stat warn"><div class="l">中风险</div><div class="v">{{d.risk['中']||0}}</div></div></div>
    <div class="card"><h3>规则命中率 / 误报率</h3><e-chart height="320px" :option="charts.bar(d.rules.map(r=>r.code),[{name:'命中率%',data:d.rules.map(r=>r.hit_rate)},{name:'误报率%',data:d.rules.map(r=>r.fp_rate)}])"/>
      <el-table :data="d.rules" size="small" border><el-table-column prop="code" label="编号" width="80"/><el-table-column prop="name" label="规则"/><el-table-column prop="hit" label="命中次数"/><el-table-column prop="hit_rate" label="命中率%"/><el-table-column prop="false_positive" label="误报次数"/><el-table-column prop="fp_rate" label="误报率%"/></el-table></div></div>`,
};

/* ---------------- 工具与插件 ---------------- */
Pages.tools = {
  components: { CrudPage },
  setup() {
    const t = reactive({ show: false, tool: null, params: '{}', res: null, file: null });
    const cols = [{ prop: 'code', label: '工具编码', required: true }, { prop: 'name', label: '名称', required: true }, { prop: 'kind', label: '类型', type: 'select', options: opts([['builtin', '内置'], ['plugin', '第三方插件']]) },
      { prop: 'protocol', label: '协议', type: 'select', options: opts(['builtin', 'rest', 'graphql', 'websocket']) }, { prop: 'endpoint', label: '接口地址', list: false },
      { prop: 'method', label: 'HTTP 方法', type: 'select', options: opts(['POST', 'GET', 'PUT']), list: false }, { prop: 'auth_type', label: '认证方式', type: 'select', options: opts([['none', '无'], ['api_key', 'X-API-Key'], ['bearer', 'Bearer Token']]), list: false },
      { prop: 'auth_value', label: '认证密钥', type: 'password', list: false }, { prop: 'params_schema', label: '参数定义(JSON)', type: 'json', list: false, tip: 'GraphQL 可在此配置 {"query":"..."}' },
      { prop: 'timeout', label: '超时(秒)', type: 'number', width: 80 }, { prop: 'provider', label: '提供方' }, { prop: 'description', label: '说明', list: false }, { prop: 'enabled', label: '启用', type: 'bool', width: 60 }];
    const actions = [{ label: '调用测试', click: (row) => { t.tool = row; t.params = JSON.stringify(row.params_schema || {}, null, 2); t.res = null; t.show = true; } }];
    const upload = async (e) => { const fd = new FormData(); fd.append('file', e.target.files[0]); const r = await api('/api/tools/upload', { method: 'POST', body: fd }); const p = JSON.parse(t.params || '{}'); p.path = r.path; t.params = JSON.stringify(p, null, 2); };
    const run = async () => { t.res = await api.post('/api/tools/invoke/' + t.tool.code, { params: JSON.parse(t.params || '{}') }); };
    return { cols, actions, t, run, upload };
  },
  template: `<div><el-alert type="info" :closable="false" style="margin-bottom:12px" title="内置工具：OCR文字识别、图片场景/图表分析、知识库检索、文档解析、文本摘要、计算器等；第三方插件支持 REST / GraphQL / WebSocket 接入（开发者可通过开放平台 API 自助注册，管理员审核启用）。"/>
    <crud-page api="/api/admin/tools" title="工具" :columns="cols" :row-actions="actions" :filters="[{prop:'kind',label:'类型',options:[{value:'builtin',label:'内置'},{value:'plugin',label:'插件'}]}]" :defaults="{kind:'plugin',protocol:'rest',method:'POST',auth_type:'none',timeout:30,enabled:true}"/>
    <el-dialog v-model="t.show" :title="'调用测试 - '+(t.tool&&t.tool.name)" width="640px"><div class="toolbar"><label class="el-button el-button--small">上传图片/文件作为 path 参数<input type="file" hidden @change="upload"/></label></div>
      <el-input v-model="t.params" type="textarea" :rows="6" style="font-family:monospace"/><el-button type="primary" style="margin-top:8px" @click="run">调用</el-button>
      <div v-if="t.res" class="mono" style="margin-top:8px">{{JSON.stringify(t.res,null,2)}}</div></el-dialog></div>`,
};

Pages.chain = {
  setup() {
    const tools = ref([]); const steps = ref([{ tool: 'datetime', params: '{}' }, { tool: 'calculator', params: '{"expression":"365*24"}' }]); const trace = ref(null); const stopOnError = ref(true);
    onMounted(async () => { tools.value = await api.get('/api/tools'); });
    const run = async () => { trace.value = (await api.post('/api/tools/chain', { steps: steps.value.map(s => ({ tool: s.tool, params: JSON.parse(s.params || '{}'), timeout: s.timeout || null })), stop_on_error: stopOnError.value })).trace; };
    return { tools, steps, trace, run, stopOnError };
  },
  template: `<div class="card"><h3>工具调度：链式调用</h3><div class="muted" style="margin-bottom:10px">后续步骤可通过 \${steps.N.字段} 引用第 N 步的输出，实现参数传递；每步可设置超时，异常时可选择中断或继续。</div>
    <div v-for="(s,i) in steps" :key="i" style="display:flex;gap:8px;margin-bottom:8px;align-items:flex-start"><el-tag>步骤 {{i}}</el-tag>
      <el-select v-model="s.tool" style="width:180px"><el-option v-for="t in tools" :key="t.code" :value="t.code" :label="t.name"/></el-select>
      <el-input v-model="s.params" type="textarea" :rows="2" placeholder='参数 JSON，如 {"text":"\${steps.0.text}"}' style="flex:1"/><el-input-number v-model="s.timeout" :min="1" placeholder="超时s" size="small"/><el-button type="danger" link @click="steps.splice(i,1)">删除</el-button></div>
    <el-button @click="steps.push({tool:'summary',params:'{}'})">+ 添加步骤</el-button> <el-checkbox v-model="stopOnError">异常时中断</el-checkbox> <el-button type="primary" @click="run">执行</el-button>
    <el-timeline v-if="trace" style="margin-top:16px"><el-timeline-item v-for="t in trace" :key="t.step" :type="t.ok?'success':'danger'" :timestamp="'步骤'+t.step+' · '+t.tool+' · '+t.ms+'ms'"><div class="mono">{{t.ok ? JSON.stringify(t.output,null,2) : t.error}}</div></el-timeline-item></el-timeline></div>`,
};

Pages.toolmetrics = {
  components: { EChart },
  setup() { const d = ref(null); onMounted(async () => { d.value = await api.get('/api/tools/metrics'); }); return { d, charts }; },
  template: `<div v-if="d"><div class="card" v-if="d.alerts.length"><h3>异常告警</h3><el-alert v-for="a in d.alerts" :key="a" :title="a" type="warning" :closable="false" style="margin-bottom:4px"/></div>
    <div class="stat-row"><div class="stat"><div class="l">服务器CPU占用</div><div class="v">{{d.resource.cpu}}%</div></div><div class="stat"><div class="l">服务器内存占用</div><div class="v">{{d.resource.mem}}%</div></div></div>
    <div class="grid2"><div class="card"><h3>调用趋势</h3><e-chart :option="Object.assign(charts.bar(d.trend.map(t=>t.day),[{name:'调用量',data:d.trend.map(t=>t.calls)},{name:'平均耗时ms',type:'line',yAxisIndex:1,data:d.trend.map(t=>t.avg_ms)}]),{yAxis:[{type:'value'},{type:'value'}]})"/></div>
      <div class="card"><h3>各工具成功率</h3><e-chart :option="charts.bar(d.tools.map(t=>t.name),[{name:'成功率%',data:d.tools.map(t=>t.success_rate)}],{yAxis:{max:100}})"/></div></div>
    <div class="card"><h3>工具性能指标</h3><el-table :data="d.tools" border size="small"><el-table-column prop="name" label="工具"/><el-table-column prop="calls" label="调用次数"/><el-table-column prop="avg_ms" label="平均响应ms"/><el-table-column prop="p95_ms" label="P95 ms"/><el-table-column prop="max_ms" label="最大ms"/><el-table-column prop="success_rate" label="成功率%"/></el-table></div>
    <div class="card"><h3>最近异常</h3><el-table :data="d.errors" size="small" border><el-table-column prop="tool_code" label="工具" width="120"/><el-table-column prop="error" label="错误"/><el-table-column prop="created_at" label="时间" width="160"/></el-table></div></div>`,
};

Pages.openapi = {
  setup() {
    const keys = ref([]); const newKey = ref('');
    const load = async () => { keys.value = await api.get('/api/tools/api-keys'); };
    const create = async () => { const { value } = await ElMessageBox.prompt('调用方名称', '创建 API Key'); newKey.value = (await api.post('/api/tools/api-keys', { name: value })).key; load(); };
    const del = async (k) => { await api.del('/api/tools/api-keys/' + k.prefix); load(); };
    onMounted(load);
    return { keys, newKey, create, del, origin: location.origin };
  },
  template: `<div><div class="card"><h3>开放平台 API Key</h3><el-button type="primary" @click="create">创建 API Key</el-button>
      <el-alert v-if="newKey" :title="'新密钥（仅显示一次）：'+newKey" type="success" :closable="false" style="margin:10px 0"/>
      <el-table :data="keys" size="small" border style="margin-top:10px"><el-table-column prop="name" label="调用方"/><el-table-column prop="prefix" label="密钥前缀"/><el-table-column prop="created" label="创建时间"/><el-table-column width="80"><template #default="{row}"><el-button link type="danger" @click="del(row)">吊销</el-button></template></el-table-column></el-table></div>
    <div class="card"><h3>第三方工具接入说明</h3><div class="mono">1) 注册工具（注册后需管理员在“工具管理”中启用）
POST {{origin}}/open/v1/plugins/register
Header: X-API-Key: &lt;你的密钥&gt;
Body: {"code":"weather","name":"天气查询","protocol":"rest|graphql|websocket","endpoint":"http://your-host/api",
       "method":"POST","auth_type":"none|api_key|bearer","auth_value":"","params_schema":{"city":"城市"},"timeout":10}

2) 调用工具
POST {{origin}}/open/v1/tools/{code}/invoke
Body: {"params":{"city":"杭州"}}

3) 接口规范：小信助手以 JSON 调用插件，插件返回 JSON 对象；REST 按 method 直传参数，
   GraphQL 以 {"query","variables"} 调用，WebSocket 发送一条 JSON 消息并读取一条响应。
   Python SDK 与示例见项目 sdk/ 目录，完整接口文档：{{origin}}/api/docs</div></div></div>`,
};

/* 布局、菜单、登录、路由 */
const MENU = [
  { title: '首页总览', key: 'dashboard' },
  { title: '终端资源管理', children: [['terminals', '终端资源清单'], ['cloud', '云桌面资源清单'], ['hwchanges', '配件更换监测'], ['indicators', '监测指标与预警'], ['alerts', '终端异常预警']] },
  { title: '终端运行监测', children: [['activity', '终端运行情况'], ['records', '终端运行数据']] },
  { title: '客户端管理', children: [['versions', '版本管理'], ['software', '装机软件管理'], ['dicts', '型号数据字典'], ['clientconfig', '客户端软件配置']] },
  { title: '消息管理', roles: ['cs'], children: [['messages', '消息列表/新建任务'], ['msgtemplates', '消息模板管理']] },
  { title: '智能运维', roles: ['cs', 'ops'], children: [['workbench', '运维工作台'], ['register', '来电登记/案例检索'], ['tickets', '工单池'], ['cases', '案例库']] },
  { title: '智能问答', roles: ['cs', 'ops'], children: [['chat', '问答测试'], ['sessions', '多轮会话管理'], ['intents', '状态跟踪(意图槽位)']] },
  { title: '模型管理', children: [['models', '模型接入与配置'], ['modelmetrics', '模型性能监控'], ['finetune', '模型微调/参数调整'], ['evaluate', '模型评估']] },
  { title: '信创知识库', children: [['kb', '知识库构建'], ['kbsearch', '检索测试与策略'], ['ragmetrics', 'RAG链路监控']] },
  { title: '合同智审', roles: ['cs', 'ops'], children: [['contracts', '合同审查'], ['rules', '审查规则管理'], ['ctemplates', '合同模板库'], ['rulestats', '规则效果监控']] },
  { title: '工具与插件', children: [['tools', '工具管理'], ['chain', '工具调度'], ['toolmetrics', '工具性能评估'], ['openapi', '插件开放平台']] },
  { title: '系统管理', children: [['users', '用户管理'], ['settings', '系统设置']] },
];

/* 菜单图标（线性 SVG，随文字颜色变化） */
const svg = (inner) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
const ICONS = {
  '首页总览': svg('<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>'),
  '终端资源管理': svg('<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>'),
  '终端运行监测': svg('<path d="M3 12h4l3-7 4 14 3-7h4"/>'),
  '客户端管理': svg('<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>'),
  '消息管理': svg('<path d="M4 5h16v11H9l-5 4z"/>'),
  '智能运维': svg('<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>'),
  '智能问答': svg('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5V14M12 17.5v.01"/>'),
  '模型管理': svg('<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>'),
  '信创知识库': svg('<path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z"/><path d="M5 18a2 2 0 0 1 2-2h12"/>'),
  '合同智审': svg('<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>'),
  '工具与插件': svg('<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><circle cx="16.5" cy="16.5" r="3.5"/>'),
  '系统管理': svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>'),
};
const LOGO = `<svg viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1664ff"/><path d="M17 15h10l20 34H37z" fill="#fff"/><path d="M47 15H37L17 49h10z" fill="#9cc0ff"/></svg>`;
const TOGGLE = svg('<path d="M10 6l-6 6 6 6M14 7h7M14 12h7M14 17h7"/>');

const Login = {
  setup() {
    const f = reactive({ username: 'admin', password: '' }); const loading = ref(false);
    const submit = async () => {
      loading.value = true;
      try {
        const r = await api.post('/api/login', f);
        store.token = r.token; store.user = r.user;
        localStorage.setItem('xx_token', r.token); localStorage.setItem('xx_user', JSON.stringify(r.user));
      } finally { loading.value = false; }
    };
    const icUser = svg('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>');
    const icLock = svg('<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>');
    return { f, submit, loading, LOGO, icUser, icLock };
  },
  template: `<div class="login-bg">
    <div class="login-left">
      <div class="hd"><span v-html="LOGO"></span><div><div class="t">小信助手管理端</div><div class="s">信创终端智能体 · 运营管理平台</div></div></div>
      <div class="orb"><span v-html="LOGO" style="display:flex"></span></div>
    </div>
    <div class="login-right"><div class="login-box">
      <div class="tab">账号登录</div>
      <el-form @submit.prevent="submit">
        <el-form-item><el-input v-model="f.username" placeholder="请输入登录账号" size="large"><template #prefix><i class="ic" v-html="icUser"></i></template></el-input></el-form-item>
        <el-form-item><el-input v-model="f.password" type="password" placeholder="请输入登录密码" size="large" show-password @keyup.enter="submit"><template #prefix><i class="ic" v-html="icLock"></i></template></el-input></el-form-item>
        <el-button type="primary" size="large" style="width:100%;margin-top:12px" :loading="loading" @click="submit">登 录</el-button>
      </el-form>
      <div class="tip">默认账号 admin / admin123</div>
    </div></div>
  </div>`,
};

const App = {
  components: Object.assign({ Login }, Pages),
  setup() {
    const route = ref(location.hash.slice(1) || 'dashboard');
    window.addEventListener('hashchange', () => { route.value = location.hash.slice(1) || 'dashboard'; });
    const collapsed = ref(false);
    const menu = computed(() => MENU.filter(m => !store.user || store.user.role === 'admin' || m.key === 'dashboard' || (m.roles && m.roles.includes(store.user.role))));
    const crumbs = computed(() => { for (const m of MENU) { if (m.key === route.value) return [m.title]; for (const c of m.children || []) if (c[0] === route.value) return [m.title, c[1]]; } return []; });
    const go = (k) => { location.hash = k; };
    const logout = () => { store.token = ''; store.user = null; localStorage.removeItem('xx_token'); localStorage.removeItem('xx_user'); };
    return { store, route, collapsed, menu, crumbs, go, logout, ROLE, ICONS, LOGO, TOGGLE };
  },
  template: `<login v-if="!store.token"/>
  <div v-else class="layout">
    <div class="topbar">
      <div class="brand"><span v-html="LOGO" style="display:flex"></span><span class="name">小信助手管理端</span></div>
      <el-dropdown trigger="click" @command="c => c==='logout' && logout()">
        <div class="user-box"><span class="avatar">{{((store.user && (store.user.real_name || store.user.username)) || '用').slice(0,1)}}</span>
          <span>{{store.user && ROLE[store.user.role]}}</span><span class="sep"></span><span>{{store.user && (store.user.real_name || store.user.username)}}</span><span class="arrow">▼</span></div>
        <template #dropdown><el-dropdown-menu><el-dropdown-item command="logout">退出登录</el-dropdown-item></el-dropdown-menu></template>
      </el-dropdown>
    </div>
    <div class="body">
      <div class="aside" :class="{collapsed}">
        <el-menu :default-active="route" :collapse="collapsed" :collapse-transition="false" @select="go" unique-opened>
          <template v-for="m in menu" :key="m.title">
            <el-menu-item v-if="m.key" :index="m.key"><i class="mi" v-html="ICONS[m.title]"></i><template #title>{{m.title}}</template></el-menu-item>
            <el-sub-menu v-else :index="m.title"><template #title><i class="mi" v-html="ICONS[m.title]"></i><span>{{m.title}}</span></template><el-menu-item v-for="c in m.children" :key="c[0]" :index="c[0]">{{c[1]}}</el-menu-item></el-sub-menu>
          </template>
        </el-menu>
      </div>
      <div class="main">
        <div class="crumb-bar"><span class="toggle" v-html="TOGGLE" @click="collapsed=!collapsed" :style="collapsed?'transform:scaleX(-1)':''"></span>
          <template v-for="(c,i) in crumbs" :key="c"><span v-if="i" class="slash">/</span><span :class="{cur:i===crumbs.length-1}">{{c}}</span></template></div>
        <div class="content"><div class="page-title">{{crumbs[crumbs.length-1]}}</div><component :is="route" :key="route"/></div>
      </div>
    </div>
  </div>`,
};

const app = Vue.createApp(App);
app.use(ElementPlus, { locale: ElementPlusLocaleZhCn });
app.config.errorHandler = (err) => { console.error(err); };
window.addEventListener('unhandledrejection', (e) => { if (e.reason && e.reason.message !== 'cancel' && e.reason !== 'cancel') console.warn(e.reason); e.preventDefault(); });
app.mount('#app');

/* 系统管理 */
Pages.users = {
  components: { CrudPage },
  setup() {
    return { cols: [{ prop: 'username', label: '账号', required: true }, { prop: 'real_name', label: '姓名' },
      { prop: 'role', label: '角色', type: 'select', options: Object.entries(ROLE).map(([value, label]) => ({ value, label })) },
      { prop: 'station', label: '保障站', type: 'select', allowCreate: true, options: opts(['市保障中心', '西湖区保障站', '上城区保障站', '拱墅区保障站']) },
      { prop: 'company', label: '供应商/厂商', tip: '纳管的供应商/厂商运维人员填写公司名' }, { prop: 'phone', label: '电话' },
      { prop: 'password_hash', label: '密码', type: 'password', list: false, tip: '新增默认 123456；编辑时不修改请保持 ******' }, { prop: 'enabled', label: '启用', type: 'bool' }, { prop: 'created_at', label: '创建时间', form: false }] };
  },
  template: `<crud-page api="/api/users" title="用户" :columns="cols" :filters="[{prop:'role',label:'角色',options:Object.entries({admin:'管理员',cs:'客服',ops:'运维',user:'普通用户'}).map(([value,label])=>({value,label}))}]" :defaults="{role:'ops',station:'市保障中心',enabled:true}"/>`,
};

Pages.settings = {
  setup() {
    const clientKey = ref(''); const pwd = reactive({ old: '', new: '' });
    onMounted(async () => { clientKey.value = (await api.get('/api/settings/client_key')).value || ''; });
    const saveKey = async () => { await api.put('/api/settings/client_key', { value: clientKey.value }); ElMessage.success('已保存'); };
    const changePwd = async () => { await api.post('/api/me/password', pwd); ElMessage.success('密码已修改'); pwd.old = pwd.new = ''; };
    return { clientKey, saveKey, pwd, changePwd, origin: location.origin };
  },
  template: `<div><div class="card"><h3>客户端接入</h3><el-form label-width="140px">
      <el-form-item label="服务端地址"><el-input :model-value="origin" readonly style="width:360px"/><div class="muted">桌面客户端 config.json 中 server 填此地址</div></el-form-item>
      <el-form-item label="客户端接入密钥"><el-input v-model="clientKey" placeholder="留空表示不校验" style="width:360px"/>&nbsp;<el-button type="primary" @click="saveKey">保存</el-button><div class="muted">设置后客户端需在 config.json 的 client_key 中配置相同值</div></el-form-item></el-form></div>
    <div class="card"><h3>修改密码</h3><el-form inline><el-form-item label="原密码"><el-input v-model="pwd.old" type="password"/></el-form-item><el-form-item label="新密码"><el-input v-model="pwd.new" type="password"/></el-form-item><el-button type="primary" @click="changePwd">修改</el-button></el-form></div>
    <div class="card"><h3>相关入口</h3><p>运维人员移动端（H5）：<a :href="origin+'/h5/'" target="_blank">{{origin}}/h5/</a></p><p>接口文档（OpenAPI）：<a :href="origin+'/api/docs'" target="_blank">{{origin}}/api/docs</a></p></div></div>`,
};

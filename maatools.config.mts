import type { FullConfig } from '@nekosu/maa-tools'

const config: FullConfig = {
  cwd: import.meta.dirname,
  maaVersion: 'latest',
  maaCache: './temp/maa-tools',
  interfacePath: 'assets/interface.json',
  check: {
    override: {
      // 同一兜底节点同时用于成功与失败收敛，是本项目的状态机设计。
      'duplicate-next': 'ignore',
      // 忽略 mpe-config 带来的报错
      // ignore warning caused by mpe-config
      // 'mpe-config': 'ignore'
    }
  }
}

export default config

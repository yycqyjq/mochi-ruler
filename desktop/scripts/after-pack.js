// Ad-hoc 签名（macOS）——见 desktop/electron-builder.yml 的说明。
// 无证书环境下 electron-builder 会跳过签名；未签名的 arm64 应用被下载后
// 会被 Gatekeeper 判「已损坏」。这里在打包组装完成后对整个 .app 做
// ad-hoc 深签名，并立即 verify 兜底。
const { execFileSync } = require('child_process')
const path = require('path')

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') {
    return
  }
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`)
  console.log(`[afterPack] ad-hoc signing: ${appPath}`)
  execFileSync('codesign', ['--force', '--deep', '--sign', '-', appPath], { stdio: 'inherit' })
  execFileSync('codesign', ['--verify', '--deep', '--strict', appPath], { stdio: 'inherit' })
  console.log('[afterPack] ad-hoc signing OK, verify passed')
}

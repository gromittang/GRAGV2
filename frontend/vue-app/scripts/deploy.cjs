const fs = require('fs')
const path = require('path')

const src = path.resolve(__dirname, '..', 'dist')
const dest = path.resolve(__dirname, '..', '..', '..', 'backend', 'static')

if (!fs.existsSync(src)) {
  console.error('ERROR: dist/ not found. Run "npm run build" first.')
  process.exit(1)
}

function copyDir(srcDir, destDir) {
  fs.mkdirSync(destDir, { recursive: true })
  for (const entry of fs.readdirSync(srcDir, { withFileTypes: true })) {
    const srcPath = path.join(srcDir, entry.name)
    const destPath = path.join(destDir, entry.name)
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath)
    } else {
      fs.copyFileSync(srcPath, destPath)
    }
  }
}

// Clean and copy
if (fs.existsSync(dest)) {
  fs.rmSync(dest, { recursive: true })
}
copyDir(src, dest)

console.log(`Deployed: ${src} → ${dest}`)
console.log('Backend static files ready for FastAPI serving.')

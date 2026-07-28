const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const batchesPath = '/Users/mac/prj/DW-SuperApps/.ua/intermediate/batches.json';
const tmpDir = '/Users/mac/prj/DW-SuperApps/.ua/tmp';
const scriptDir = '/Users/mac/prj/DW-SuperApps/projects/ua/understand-anything-plugin/skills/understand';

const batches = JSON.parse(fs.readFileSync(batchesPath, 'utf8'));
const results = [];

for (let i = 1; i <= 23; i++) {
  const batch = batches.batches.find(b => b.batchIndex === i);
  if (!batch) {
    results.push({ batch: i, status: 'FAILED', error: 'Batch not found' });
    continue;
  }

  const input = {
    projectRoot: '/Users/mac/prj/DW-SuperApps',
    batchFiles: batch.files,
    batchImportData: batch.batchImportData,
    neighborMap: batch.neighborMap
  };

  const inputPath = path.join(tmpDir, `ua-file-analyzer-input-${i}.json`);
  const outputPath = path.join(tmpDir, `ua-file-extract-results-${i}.json`);

  fs.writeFileSync(inputPath, JSON.stringify(input, null, 2));

  try {
    execSync(
      `node extract-structure.mjs "${inputPath}" "${outputPath}"`,
      { cwd: scriptDir, stdio: ['pipe', 'pipe', 'pipe'] }
    );
    results.push({ batch: i, status: 'SUCCESS', input: inputPath, output: outputPath });
  } catch (err) {
    const stderr = err.stderr?.toString() || err.message;
    results.push({ batch: i, status: 'FAILED', error: stderr });
  }
}

console.log(JSON.stringify(results, null, 2));

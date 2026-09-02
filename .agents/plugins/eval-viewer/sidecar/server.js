import express from 'express';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Walk up until we find the project root containing 'agents' directory
function findWorkspaceRoot(startDir) {
  let current = startDir;
  while (current !== path.dirname(current)) {
    if (fs.existsSync(path.join(current, 'agents')) && fs.statSync(path.join(current, 'agents')).isDirectory()) {
      return current;
    }
    current = path.dirname(current);
  }
  return path.resolve(__dirname, '../../../..');
}

const WORKSPACE_ROOT = findWorkspaceRoot(__dirname);
const AGENTS_DIR = path.join(WORKSPACE_ROOT, 'agents');

const app = express();
const PORT = process.env.PORT || 8088;

/**
 * Scan all agents and extract evaluation reports with summary metadata.
 */
function getEvaluationReports() {
  const results = {};

  if (!fs.existsSync(AGENTS_DIR)) {
    return results;
  }

  const agentFolders = fs.readdirSync(AGENTS_DIR, { withFileTypes: true })
    .filter(dirent => dirent.isDirectory())
    .map(dirent => dirent.name);

  for (const agent of agentFolders) {
    const gradeResultsDir = path.join(AGENTS_DIR, agent, 'artifacts', 'grade_results');
    if (!fs.existsSync(gradeResultsDir)) {
      continue;
    }

    const files = fs.readdirSync(gradeResultsDir);
    const htmlFiles = files.filter(f => f.endsWith('.html'));

    const reports = [];

    for (const htmlFile of htmlFiles) {
      const baseName = htmlFile.replace('.html', '');
      const jsonFile = `${baseName}.json`;
      const htmlPath = path.join(gradeResultsDir, htmlFile);
      const jsonPath = path.join(gradeResultsDir, jsonFile);

      const stats = fs.statSync(htmlPath);
      let summary = null;

      if (fs.existsSync(jsonPath)) {
        try {
          const jsonContent = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
          let metricsList = [];
          if (Array.isArray(jsonContent.summary_metrics)) {
            metricsList = jsonContent.summary_metrics;
          } else if (jsonContent.summary_metrics && typeof jsonContent.summary_metrics === 'object') {
            metricsList = Object.entries(jsonContent.summary_metrics).map(([k, v]) => ({ metric_name: k, ...v }));
          }

          summary = {
            dataset: jsonContent.evaluation_dataset?.eval_dataset_id || 'default',
            summaryMetrics: metricsList,
            evalCaseCount: Array.isArray(jsonContent.eval_case_results) ? jsonContent.eval_case_results.length : null,
          };
        } catch (e) {
          // ignore corrupted JSON
        }
      }

      // Parse timestamp from results_YYYYMMDD_HHMMSS
      const match = baseName.match(/results_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
      let formattedDate = stats.mtime.toLocaleString();
      let isoTimestamp = stats.mtime.toISOString();
      if (match) {
        const [_, year, month, day, hour, min, sec] = match;
        const d = new Date(Date.UTC(+year, +month - 1, +day, +hour, +min, +sec));
        formattedDate = d.toLocaleString();
        isoTimestamp = d.toISOString();
      }

      reports.push({
        agent,
        filename: htmlFile,
        jsonFilename: fs.existsSync(jsonPath) ? jsonFile : null,
        created: isoTimestamp,
        formattedDate,
        sizeBytes: stats.size,
        summary
      });
    }

    // Sort descending by created date
    reports.sort((a, b) => new Date(b.created) - new Date(a.created));

    if (reports.length > 0) {
      results[agent] = reports;
    }
  }

  return results;
}

// API endpoint returning all reports in JSON format
app.get('/api/reports', (req, res) => {
  res.json(getEvaluationReports());
});

// View the latest report for an agent directly
app.get('/view/:agent/latest', (req, res) => {
  const { agent } = req.params;
  const reports = getEvaluationReports()[agent] || [];
  if (reports.length === 0) {
    return res.status(404).send(`No evaluation reports found for agent: ${agent}`);
  }
  res.redirect(`/reports/${agent}/${reports[0].filename}`);
});

// View a specific report in iframe with top navigation header
app.get('/view/:agent/:filename', (req, res) => {
  const { agent, filename } = req.params;
  const reports = getEvaluationReports()[agent] || [];
  const current = reports.find(r => r.filename === filename);

  res.send(`
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${agent} - ${filename}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: #0f172a; color: #f8fafc; }
    header { background: #1e293b; border-bottom: 1px solid #334155; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; }
    .title-group { display: flex; align-items: center; gap: 12px; }
    .badge { background: #3b82f6; color: #fff; font-size: 12px; padding: 3px 8px; border-radius: 4px; font-weight: 600; }
    .nav-btn { background: #334155; color: #f8fafc; border: none; padding: 6px 14px; border-radius: 6px; text-decoration: none; font-size: 13px; font-weight: 500; transition: background 0.2s; }
    .nav-btn:hover { background: #475569; }
    .raw-btn { background: #0ea5e9; }
    .raw-btn:hover { background: #0284c7; }
    iframe { flex: 1; width: 100%; border: none; background: #fff; }
  </style>
</head>
<body>
  <header>
    <div class="title-group">
      <a href="/" class="nav-btn">← Back to Dashboard</a>
      <span class="badge">${agent}</span>
      <strong>${filename}</strong>
      ${current ? `<span style="color: #94a3b8; font-size: 13px;">${current.formattedDate}</span>` : ''}
    </div>
    <div style="display: flex; gap: 10px;">
      ${current && current.jsonFilename ? `<a href="/json/${agent}/${current.jsonFilename}" class="nav-btn" target="_blank">Download JSON</a>` : ''}
      <a href="/reports/${agent}/${filename}" class="nav-btn raw-btn" target="_blank">Open Raw Report ↗</a>
    </div>
  </header>
  <iframe src="/reports/${agent}/${filename}"></iframe>
</body>
</html>
  `);
});

// Serve raw HTML files
app.get('/reports/:agent/:filename', (req, res) => {
  const { agent, filename } = req.params;
  const filePath = path.join(AGENTS_DIR, agent, 'artifacts', 'grade_results', filename);

  if (!fs.existsSync(filePath) || !filename.endsWith('.html')) {
    return res.status(404).send('Report not found.');
  }

  res.sendFile(filePath);
});

// Serve raw JSON files
app.get('/json/:agent/:filename', (req, res) => {
  const { agent, filename } = req.params;
  const filePath = path.join(AGENTS_DIR, agent, 'artifacts', 'grade_results', filename);

  if (!fs.existsSync(filePath) || !filename.endsWith('.json')) {
    return res.status(404).send('JSON file not found.');
  }

  res.sendFile(filePath);
});

// Main Dashboard
app.get('/', (req, res) => {
  const allReports = getEvaluationReports();
  const agents = Object.keys(allReports);

  res.send(`
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Luncher Agent Evaluation Dashboard</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --success: #10b981;
      --warning: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 30px 20px; }
    .container { max-width: 1200px; margin: 0 auto; }
    header { margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 20px; }
    h1 { font-size: 26px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
    .subtitle { color: var(--text-muted); font-size: 14px; margin-top: 5px; }
    .status-pill { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
    .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 0 rgba(16, 185, 129, 0.7); animation: pulse 1.5s infinite; }
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); } 70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
    
    .agent-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 24px; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .agent-name { font-size: 20px; font-weight: 600; color: #38bdf8; display: flex; align-items: center; gap: 10px; }
    .latest-btn { background: var(--primary); color: #fff; padding: 8px 18px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 600; transition: background 0.2s; display: inline-flex; align-items: center; gap: 6px; }
    .latest-btn:hover { background: var(--primary-hover); }

    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .stat-box { background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }
    .stat-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-value { font-size: 18px; font-weight: 700; margin-top: 4px; color: #fff; }

    table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
    th { text-align: left; padding: 10px 14px; background: rgba(15, 23, 42, 0.4); color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
    td { padding: 12px 14px; border-bottom: 1px solid rgba(51, 65, 85, 0.5); vertical-align: middle; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    
    .metric-badge { display: inline-block; background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 500; margin: 2px 4px 2px 0; }
    .score-pill { display: inline-block; background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 600; }
    .action-link { color: #38bdf8; text-decoration: none; font-weight: 600; margin-right: 12px; font-size: 13px; }
    .action-link:hover { text-decoration: underline; }
    .empty-state { text-align: center; padding: 50px; color: var(--text-muted); }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>📊 ADK Agent Evaluation Dashboard</h1>
        <div class="subtitle">Antigravity Sidecar Plugin • Port ${PORT}</div>
      </div>
      <div class="status-pill">
        <div class="pulse"></div>
        <span>Live Sidecar: Active</span>
      </div>
    </header>

    ${agents.length === 0 ? `
      <div class="agent-card empty-state">
        <h2>No evaluation results found yet</h2>
        <p style="margin-top: 10px;">Run <code>agents-cli eval grade</code> in any agent to generate report cards.</p>
      </div>
    ` : agents.map(agent => {
      const reports = allReports[agent];
      const latest = reports[0];
      const latestSummary = latest.summary;

      return `
        <div class="agent-card">
          <div class="card-header">
            <div>
              <div class="agent-name">🤖 ${agent}</div>
              <div style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">
                ${reports.length} report(s) recorded • Latest: ${latest.formattedDate}
              </div>
            </div>
            <a href="/view/${agent}/${latest.filename}" class="latest-btn">
              ⚡ Open Latest Report
            </a>
          </div>

          ${latestSummary ? `
            <div class="summary-grid">
              <div class="stat-box">
                <div class="stat-label">Total Test Cases</div>
                <div class="stat-value">${latestSummary.evalCaseCount || 'N/A'}</div>
              </div>
              ${(latestSummary.summaryMetrics || []).map(m => `
                <div class="stat-box">
                  <div class="stat-label">${m.metric_name}</div>
                  <div class="stat-value" style="color: ${m.pass_rate === 1.0 ? 'var(--success)' : '#fff'};">
                    ${m.pass_rate !== undefined && m.pass_rate !== null ? `${(m.pass_rate * 100).toFixed(0)}% Pass` : (m.mean_score !== undefined ? m.mean_score.toFixed(2) : '✓')}
                  </div>
                </div>
              `).join('')}
            </div>
          ` : ''}

          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Run Report File</th>
                <th>Metrics Evaluated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${reports.map((report, idx) => `
                <tr>
                  <td>
                    <strong>${report.formattedDate}</strong>
                    ${idx === 0 ? '<span style="margin-left: 8px; font-size: 11px; background: #3b82f6; padding: 2px 6px; border-radius: 4px;">LATEST</span>' : ''}
                  </td>
                  <td><code>${report.filename}</code></td>
                  <td>
                    ${report.summary && report.summary.summaryMetrics && report.summary.summaryMetrics.length > 0 ? 
                      report.summary.summaryMetrics.map(m => `<span class="metric-badge">${m.metric_name}</span>`).join('') 
                      : '<span style="color: var(--text-muted); font-size: 12px;">Standard Suite</span>'}
                  </td>
                  <td>
                    <a href="/view/${agent}/${report.filename}" class="action-link">Interactive View</a>
                    <a href="/reports/${agent}/${report.filename}" target="_blank" class="action-link" style="color: #94a3b8;">Raw HTML</a>
                    ${report.jsonFilename ? `<a href="/json/${agent}/${report.jsonFilename}" target="_blank" class="action-link" style="color: #94a3b8;">JSON</a>` : ''}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }).join('')}
  </div>
</body>
</html>
  `);
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Eval Server Sidecar] Running on http://localhost:${PORT}`);
  console.log(`[Eval Server Sidecar] Serving grade results from ${AGENTS_DIR}`);
});

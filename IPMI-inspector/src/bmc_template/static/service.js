/**
 * Shared BMC tool service helpers (shutdown, etc.)
 */
async function shutdownToolService(serviceName) {
  const name = serviceName || window.BMC_SERVICE_NAME || 'BMC 工具服務';
  if (!confirm(`確定要關閉整個 ${name}？\n（會結束背景程式與系統匣圖示）`)) return;

  const url = window.SERVICE_SHUTDOWN_URL || '/api/service/shutdown';
  try {
    const r = await fetch(url, { method: 'POST' });
    if (r.ok) await r.json().catch(() => ({}));
  } catch (_) {
    /* 服務結束時連線中斷屬正常 */
  }
  document.body.innerHTML =
    '<div style="display:flex;height:100vh;align-items:center;justify-content:center;' +
    'font-family:monospace;color:#94a3b8;text-align:center;padding:24px;">' +
    `${name} 已結束，可關閉此分頁。</div>`;
}

window.shutdownToolService = shutdownToolService;

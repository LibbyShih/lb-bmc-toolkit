function renderAnnotation(annotation) {
  if (!annotation) return '<div class="spec-placeholder"><p>No spec annotation available.</p></div>';

  let html = '<div class="hex-dump">';
  if (annotation.fields) {
    annotation.fields.forEach(f => {
      const tooltip = `${f.name}: ${f.decoded}${f.note ? '\n' + f.note : ''}`;
      html += `<span class="hex-field color-${f.color}" title="${tooltip.replace(/"/g,'&quot;')}">${f.bytes_hex}</span> `;
    });
  }
  if (annotation.unmatched_bytes) {
    html += `<span class="hex-unmatched" title="Unmatched bytes">${annotation.unmatched_bytes}</span>`;
  }
  html += '</div>';

  html += '<div class="hex-legend"><ul>';
  if (annotation.fields) {
    annotation.fields.forEach(f => {
      html += `<li><span class="color-swatch color-${f.color}"></span><strong>${f.name}</strong>: ${f.decoded}`;
      if (f.note) html += `<span style="color:var(--text-muted);margin-left:4px;">${f.note}</span>`;
      html += '</li>';
    });
  }
  html += '</ul></div>';
  return html;
}

function updateSpecPanel(title, annotation) {
  const titleEl = document.getElementById('spec-title');
  if (titleEl) titleEl.textContent = '◈ SPEC 解析 — ' + title;
  const contentDiv = document.getElementById('spec-content');
  if (!contentDiv) return;
  contentDiv.innerHTML = renderAnnotation(annotation);
  openSpecPanel();
}

function clearSpecPanel() {
  const titleEl = document.getElementById('spec-title');
  if (titleEl) titleEl.textContent = '◈ SPEC 解析';
  const contentDiv = document.getElementById('spec-content');
  if (contentDiv) contentDiv.innerHTML = '<div class="spec-placeholder"><p>點任何資料項目查看 Spec 解析</p></div>';
  document.getElementById('spec-pane')?.classList.remove('open');
}

function openSpecPanel() {
  document.getElementById('spec-pane')?.classList.add('open');
}

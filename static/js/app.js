// ==========================================================================
// FB TRACKING NO-API — CLIENT APPLICATION JAVASCRIPT
// ==========================================================================

let uploadedMemberFile = null;
let uploadedPostFile = null;
let trackingData = null;
let currentReportDownloadUrl = "";

function toggleCookieGuide() {
  const box = document.getElementById('cookie-guide-box');
  if (box) {
    box.style.display = box.style.display === 'none' ? 'block' : 'none';
  }
}

function togglePostInputMode(mode) {
  const boxText = document.getElementById('box-post-text');
  const boxFile = document.getElementById('box-post-file');
  const btnText = document.getElementById('btn-mode-text');
  const btnFile = document.getElementById('btn-mode-file');

  if (mode === 'text') {
    boxText.style.display = 'block';
    boxFile.style.display = 'none';
    btnText.className = 'btn btn-sm btn-primary';
    btnFile.className = 'btn btn-sm btn-secondary';
  } else {
    boxText.style.display = 'none';
    boxFile.style.display = 'block';
    btnText.className = 'btn btn-sm btn-secondary';
    btnFile.className = 'btn btn-sm btn-primary';
  }
}

function handleMemberFile(event) {
  const file = event.target.files[0];
  const statusEl = document.getElementById('member-file-status');
  if (file) {
    uploadedMemberFile = file;
    statusEl.innerHTML = `<i class="fa-solid fa-circle-check"></i> Đã chọn: ${file.name} (${(file.size/1024).toFixed(1)} KB)`;
  }
}

function handlePostFile(event) {
  const file = event.target.files[0];
  const statusEl = document.getElementById('post-file-status');
  if (file) {
    uploadedPostFile = file;
    statusEl.innerHTML = `<i class="fa-solid fa-circle-check"></i> Đã chọn: ${file.name} (${(file.size/1024).toFixed(1)} KB)`;
  }
}

function appendLog(message, level = 'info') {
  const screen = document.getElementById('terminal-screen');
  if (!screen) return;

  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];

  const div = document.createElement('div');
  div.className = `log-entry log-${level}`;
  div.innerHTML = `<span style="color: #64748b; font-size: 0.75rem;">[${timeStr}]</span> <span>${escapeHtml(message)}</span>`;
  
  screen.appendChild(div);
  screen.scrollTop = screen.scrollHeight;
}

function clearLogs() {
  const screen = document.getElementById('terminal-screen');
  if (screen) {
    screen.innerHTML = '<div style="color: var(--text-muted);">Đã làm sạch nhật ký. Sẵn sàng quét...</div>';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function checkCookie() {
  const cookieInput = document.getElementById('fb_cookie');
  const statusEl = document.getElementById('cookie-status-msg');
  const btn = document.getElementById('btn-check-cookie');
  const cookie = (cookieInput ? cookieInput.value : '').trim();

  if (!cookie) {
    alert('Vui lòng dán Cookie Facebook vào ô trước khi kiểm tra!');
    return;
  }

  statusEl.style.color = '#fbbf24';
  statusEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang kiểm tra...';
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/check-cookie', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cookie: cookie })
    });
    const data = await res.json();
    if (data.valid) {
      statusEl.style.color = '#34d399';
      statusEl.innerHTML = `<i class="fa-solid fa-circle-check"></i> Hợp lệ: <strong>${escapeHtml(data.name)}</strong> (c_user: ${data.user_id})`;
      appendLog(`🍪 Đã xác thực Cookie Facebook: ${data.name} (c_user: ${data.user_id})`, 'success');
    } else {
      statusEl.style.color = '#f87171';
      statusEl.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> ${escapeHtml(data.message)}`;
      appendLog(`❌ Lỗi Cookie: ${data.message}`, 'error');
    }
  } catch (err) {
    statusEl.style.color = '#f87171';
    statusEl.innerText = 'Lỗi kết nối máy chủ';
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function startTracking() {
  const cookie = (document.getElementById('fb_cookie').value || '').trim();
  const postUrlsText = (document.getElementById('post_urls').value || '').trim();
  const checkLikes = document.getElementById('check_likes').checked;
  const checkComments = document.getElementById('check_comments').checked;
  const checkShares = document.getElementById('check_shares').checked;
  const btnStart = document.getElementById('btn-start-track');

  if (!postUrlsText && !uploadedPostFile) {
    alert('Vui lòng nhập ít nhất 1 link bài viết Facebook hoặc tải lên file Excel bài viết!');
    return;
  }

  clearLogs();
  appendLog('🚀 Khởi động tiến trình Tracking Facebook Không Cần API...', 'info');

  btnStart.disabled = true;
  btnStart.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Cào Dữ Liệu...';

  const formData = new FormData();
  formData.append('cookie', cookie);
  formData.append('post_urls', postUrlsText);
  formData.append('check_likes', checkLikes ? '1' : '0');
  formData.append('check_comments', checkComments ? '1' : '0');
  formData.append('check_shares', checkShares ? '1' : '0');

  if (uploadedMemberFile) {
    formData.append('member_file', uploadedMemberFile);
  }
  if (uploadedPostFile) {
    formData.append('post_file', uploadedPostFile);
  }

  try {
    const res = await fetch('/api/start-tracking', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (data.success) {
      trackingData = data;
      currentReportDownloadUrl = data.report_download_url || '';

      // Hiển thị các log
      if (data.logs && Array.isArray(data.logs)) {
        data.logs.forEach(l => appendLog(l.msg, l.level));
      }

      appendLog(`🎉 Hoàn tất cào và đối soát! Đã xử lý ${data.total_posts} bài viết với ${data.total_members} thành viên.`, 'success');

      // Hiển thị kết quả lên 3 Tab
      renderResults(data);
      document.getElementById('results-container').style.display = 'block';
      document.getElementById('results-container').scrollIntoView({ behavior: 'smooth' });

    } else {
      appendLog(`❌ Lỗi: ${data.error || 'Quá trình quét thất bại'}`, 'error');
      alert('Lỗi: ' + (data.error || 'Quá trình quét thất bại'));
    }
  } catch (err) {
    appendLog(`❌ Lỗi kết nối máy chủ: ${err}`, 'error');
    alert('Lỗi kết nối máy chủ: ' + err);
  } finally {
    btnStart.disabled = false;
    btnStart.innerHTML = '<i class="fa-solid fa-play"></i> Bắt Đầu Quét Tương Tác';
  }
}

function renderResults(data) {
  // 1. Tab Chi tiết thành viên
  const memBody = document.getElementById('table-members-body');
  if (memBody && data.match_results) {
    if (data.match_results.length === 0) {
      memBody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 20px; color: var(--text-muted);">Không có thành viên nào trong danh sách</td></tr>';
    } else {
      let html = '';
      data.match_results.forEach(r => {
        let statusBadge = '';
        if (r.trang_thai === 'da_tat_ca' || r.trang_thai === 'da_comment_va_like') {
          statusBadge = '<span style="background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">Đầy đủ</span>';
        } else if (r.trang_thai === 'chua_tuong_tac') {
          statusBadge = '<span style="background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">Chưa làm</span>';
        } else {
          statusBadge = '<span style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">1 phần</span>';
        }

        html += `
          <tr style="border-bottom: 1px solid var(--border-subtle);">
            <td style="padding: 10px 14px; font-weight: 600; color: #fff;">${escapeHtml(r.ho_ten)}</td>
            <td style="padding: 10px 14px; font-family: var(--font-mono); font-size: 0.8rem; color: #93c5fd;">${escapeHtml(r.facebook_id || '-')}</td>
            <td style="padding: 10px 14px;">
              <div style="font-weight: 600; color: #cbd5e1;">${escapeHtml(r.mo_ta || r.post_id)}</div>
              ${r.permalink_url ? `<a href="${r.permalink_url}" target="_blank" style="font-size: 0.75rem; color: #38bdf8;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Xem bài</a>` : ''}
            </td>
            <td style="padding: 10px 14px; text-align: center;">
              ${r.da_like ? `<span style="color: #ef4444;"><i class="fa-solid fa-heart"></i> ${escapeHtml(r.loai_reaction || 'LIKE')}</span>` : '<span style="color: #64748b;">-</span>'}
            </td>
            <td style="padding: 10px 14px; text-align: center;">
              ${r.da_comment ? `<span style="color: #38bdf8;" title="${escapeHtml(r.noi_dung_comment)}"><i class="fa-solid fa-comment"></i> ${r.so_comment} cmt</span>` : '<span style="color: #64748b;">-</span>'}
            </td>
            <td style="padding: 10px 14px; text-align: center;">
              ${r.da_share ? '<span style="color: #f59e0b;"><i class="fa-solid fa-share"></i> Có</span>' : '<span style="color: #64748b;">-</span>'}
            </td>
            <td style="padding: 10px 14px; text-align: center;">${statusBadge}</td>
          </tr>
        `;
      });
      memBody.innerHTML = html;
    }
  }

  // 2. Tab Người lạ tương tác
  const strBody = document.getElementById('table-strangers-body');
  if (strBody && data.strangers) {
    if (data.strangers.length === 0) {
      strBody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: var(--text-muted);">Không phát hiện người lạ tương tác</td></tr>';
    } else {
      let html = '';
      data.strangers.forEach(s => {
        html += `
          <tr class="row-stranger" data-type="${s.loai_tuong_tac.toLowerCase()}" style="border-bottom: 1px solid var(--border-subtle);">
            <td style="padding: 10px 14px; font-weight: 600; color: #fff;">${escapeHtml(s.nguoi_dung)}</td>
            <td style="padding: 10px 14px; font-family: var(--font-mono); font-size: 0.8rem; color: #93c5fd;">
              ${s.facebook_id ? `<a href="https://facebook.com/${s.facebook_id}" target="_blank" style="color: #38bdf8;">${escapeHtml(s.facebook_id)}</a>` : '-'}
            </td>
            <td style="padding: 10px 14px; color: #cbd5e1;">${escapeHtml(s.mo_ta || s.post_id)}</td>
            <td style="padding: 10px 14px; text-align: center;">
              <span style="background: rgba(99, 102, 241, 0.15); color: #818cf8; padding: 2px 8px; border-radius: 9999px; font-size: 0.78rem;">
                ${escapeHtml(s.loai_tuong_tac)}
              </span>
            </td>
            <td style="padding: 10px 14px; color: #e2e8f0; font-size: 0.8rem;">${escapeHtml(s.noi_dung)}</td>
          </tr>
        `;
      });
      strBody.innerHTML = html;
    }
  }

  // 3. Tab Tổng hợp bài viết
  const postBody = document.getElementById('table-posts-body');
  if (postBody && data.post_summary) {
    let html = '';
    data.post_summary.forEach(p => {
      html += `
        <tr style="border-bottom: 1px solid var(--border-subtle);">
          <td style="padding: 10px 14px; font-weight: 600; color: #fff;">${escapeHtml(p.mo_ta || p.post_id)}</td>
          <td style="padding: 10px 14px;">
            ${p.permalink_url ? `<a href="${p.permalink_url}" target="_blank" style="color: #38bdf8;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Mở bài viết</a>` : '-'}
          </td>
          <td style="padding: 10px 14px; text-align: center; color: #ef4444; font-weight: 700;">${p.likes_count}</td>
          <td style="padding: 10px 14px; text-align: center; color: #38bdf8; font-weight: 700;">${p.comments_count}</td>
          <td style="padding: 10px 14px; text-align: center; color: #f59e0b; font-weight: 700;">${p.shares_count}</td>
          <td style="padding: 10px 14px; text-align: center;">
            <div style="display: flex; align-items: center; justify-content: center; gap: 6px;">
              <div style="width: 50px; background: rgba(255,255,255,0.1); border-radius: 4px; height: 6px; overflow: hidden;">
                <div style="width: ${p.completion_rate}%; background: #10b981; height: 100%;"></div>
              </div>
              <span style="font-weight: 700; color: #34d399; font-size: 0.8rem;">${p.completion_rate}%</span>
            </div>
          </td>
        </tr>
      `;
    });
    postBody.innerHTML = html;
  }
}

function switchResultTab(tabName) {
  const tabMembers = document.getElementById('tab-view-members');
  const tabStrangers = document.getElementById('tab-view-strangers');
  const tabPosts = document.getElementById('tab-view-posts');

  const btnMembers = document.getElementById('tab-btn-members');
  const btnStrangers = document.getElementById('tab-btn-strangers');
  const btnPosts = document.getElementById('tab-btn-posts');

  [tabMembers, tabStrangers, tabPosts].forEach(t => t.style.display = 'none');
  [btnMembers, btnStrangers, btnPosts].forEach(b => b.className = 'btn btn-sm btn-secondary');

  if (tabName === 'members') {
    tabMembers.style.display = 'block';
    btnMembers.className = 'btn btn-sm btn-primary';
  } else if (tabName === 'strangers') {
    tabStrangers.style.display = 'block';
    btnStrangers.className = 'btn btn-sm btn-primary';
  } else if (tabName === 'posts') {
    tabPosts.style.display = 'block';
    btnPosts.className = 'btn btn-sm btn-primary';
  }
}

function filterStrangers(type) {
  const rows = document.querySelectorAll('.row-stranger');
  rows.forEach(r => {
    const rType = r.getAttribute('data-type') || '';
    if (type === 'all') {
      r.style.display = '';
    } else if (type === 'like' && (rType.includes('like') || rType.includes('react'))) {
      r.style.display = '';
    } else if (type === 'comment' && rType.includes('comment')) {
      r.style.display = '';
    } else {
      r.style.display = 'none';
    }
  });
}

function exportExcelReport() {
  if (currentReportDownloadUrl) {
    window.location.href = currentReportDownloadUrl;
  } else {
    alert('Không tìm thấy file báo cáo. Vui lòng thực hiện quét trước!');
  }
}

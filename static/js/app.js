// ==========================================================================
// FB TRACKING NO-API — CLIENT APPLICATION JAVASCRIPT
// ==========================================================================

let currentTargetMode = 'page';
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

function setTrackingTargetMode(mode) {
  currentTargetMode = mode;
  const boxPage = document.getElementById('box-target-page');
  const boxPosts = document.getElementById('box-target-posts');
  const btnPage = document.getElementById('btn-target-page');
  const btnPosts = document.getElementById('btn-target-posts');

  if (mode === 'page') {
    if (boxPage) boxPage.style.display = 'block';
    if (boxPosts) boxPosts.style.display = 'none';
    if (btnPage) btnPage.className = 'btn btn-sm btn-primary';
    if (btnPosts) btnPosts.className = 'btn btn-sm btn-secondary';
  } else {
    if (boxPage) boxPage.style.display = 'none';
    if (boxPosts) boxPosts.style.display = 'block';
    if (btnPage) btnPage.className = 'btn btn-sm btn-secondary';
    if (btnPosts) btnPosts.className = 'btn btn-sm btn-primary';
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
  const fanpageUrl = (document.getElementById('fanpage_url') ? document.getElementById('fanpage_url').value : '').trim();
  const maxPosts = document.getElementById('max_posts') ? document.getElementById('max_posts').value : '0';
  const postUrlsText = (document.getElementById('post_urls') ? document.getElementById('post_urls').value : '').trim();
  const checkLikes = document.getElementById('check_likes').checked;
  const checkComments = document.getElementById('check_comments').checked;
  const checkShares = document.getElementById('check_shares').checked;
  const btnStart = document.getElementById('btn-start-track');

  if (currentTargetMode === 'page') {
    if (!fanpageUrl) {
      alert('Vui lòng nhập đường dẫn Fanpage hoặc ID Trang Facebook!');
      return;
    }
  } else {
    if (!postUrlsText && !uploadedPostFile) {
      alert('Vui lòng nhập ít nhất 1 link bài viết Facebook hoặc tải lên file Excel bài viết!');
      return;
    }
  }

  clearLogs();
  appendLog('🚀 Khởi động tiến trình Tracking Facebook Không Cần API...', 'info');

  btnStart.disabled = true;
  btnStart.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Cào Dữ Liệu...';

  const formData = new FormData();
  formData.append('cookie', cookie);
  formData.append('mode', currentTargetMode);
  formData.append('page_url', fanpageUrl);
  formData.append('max_posts', maxPosts);
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

    const textResp = await res.text();
    let data;
    try {
      data = JSON.parse(textResp);
    } catch (parseErr) {
      console.error('Non-JSON response:', textResp);
      let errMsg = `Lỗi phản hồi từ máy chủ (${res.status})`;
      if (res.status === 504 || textResp.includes('504') || textResp.includes('TIMEOUT')) {
        errMsg = 'Máy chủ phản hồi chậm (504 Timeout). Hệ thống đã tối ưu, vui lòng bấm thử lại!';
      } else if (res.status === 401) {
        errMsg = 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại!';
        window.location.href = '/login';
        return;
      }
      appendLog(`❌ ${errMsg}`, 'error');
      alert(errMsg);
      return;
    }

    if (data.success) {
      trackingData = data;
      currentReportDownloadUrl = data.report_download_url || '';

      // Hiển thị các log
      if (data.logs && Array.isArray(data.logs)) {
        data.logs.forEach(l => appendLog(l.msg, l.level));
      }

      appendLog(`🎉 Hoàn tất cào và tổng hợp! Đã phân tích ${data.total_posts} bài viết với ${data.total_users_interacted || (data.users_directory || []).length} người tương tác.`, 'success');

      // Hiển thị kết quả lên giao diện
      renderResults(data);
      document.getElementById('results-container').style.display = 'block';
      document.getElementById('results-container').scrollIntoView({ behavior: 'smooth' });

    } else {
      if (data.logs && Array.isArray(data.logs)) {
        data.logs.forEach(l => appendLog(l.msg, l.level));
      }
      appendLog(`❌ Lỗi: ${data.error || 'Quá trình quét thất bại'}`, 'error');
      alert('Lỗi: ' + (data.error || 'Quá trình quét thất bại'));
    }
  } catch (err) {
    appendLog(`❌ Lỗi kết nối: ${err}`, 'error');
    alert('Lỗi kết nối: ' + err);
  } finally {
    btnStart.disabled = false;
    btnStart.innerHTML = '<i class="fa-solid fa-play"></i> Bắt Đầu Quét Tương Tác';
  }
}

let allPostsDetails = [];
let allUsersDirectory = [];
let currentUserFilterType = 'all';
let currentSelectedPostIndex = 0;
let currentPostFilterType = 'all';

function renderResults(data) {
  allPostsDetails = data.posts_details || [];
  allUsersDirectory = data.users_directory || [];
  
  // 1. Cập nhật số liệu tổng quan toàn trang (Thẻ thống kê)
  const statUsers = document.getElementById('stat-total-users');
  const statPosts = document.getElementById('stat-total-posts');
  const statLikes = document.getElementById('stat-total-likes');
  const statCmts = document.getElementById('stat-total-comments');
  const statShares = document.getElementById('stat-total-shares');

  let totalLikes = 0;
  let totalCmts = 0;
  let totalShares = 0;
  allPostsDetails.forEach(p => {
    totalLikes += (p.likes_count || 0);
    totalCmts += (p.comments_count || 0);
    totalShares += (p.shares_count || 0);
  });

  if (statUsers) statUsers.innerText = allUsersDirectory.length;
  if (statPosts) statPosts.innerText = allPostsDetails.length;
  if (statLikes) statLikes.innerText = totalLikes;
  if (statCmts) statCmts.innerText = totalCmts;
  if (statShares) statShares.innerText = totalShares;

  // 2. Cập nhật số lượng người theo từng bộ lọc ở Tab 1
  const uCntAll = document.getElementById('user-cnt-all');
  const uCntLike = document.getElementById('user-cnt-like');
  const uCntCmt = document.getElementById('user-cnt-comment');
  const uCntShare = document.getElementById('user-cnt-share');

  if (uCntAll) uCntAll.innerText = allUsersDirectory.length;
  if (uCntLike) uCntLike.innerText = allUsersDirectory.filter(u => u.likes_count > 0).length;
  if (uCntCmt) uCntCmt.innerText = allUsersDirectory.filter(u => u.comments_count > 0).length;
  if (uCntShare) uCntShare.innerText = allUsersDirectory.filter(u => u.shares_count > 0).length;

  // Render bảng danh sách Tên Người Dùng Toàn Trang (Tab 1)
  currentUserFilterType = 'all';
  renderUsersDirectoryTable();

  // 3. Render Tab 2: Danh sách thẻ bài viết (Post Cards)
  const countEl = document.getElementById('inspector-posts-count');
  if (countEl) countEl.innerText = `${allPostsDetails.length} bài viết đã quét`;

  const cardsContainer = document.getElementById('inspector-post-cards');
  if (cardsContainer) {
    if (allPostsDetails.length === 0) {
      cardsContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">Không có bài viết nào được quét.</div>';
    } else {
      let cardsHtml = '';
      allPostsDetails.forEach((p, idx) => {
        cardsHtml += `
          <div class="post-item-card" id="post-card-${idx}" onclick="selectInspectorPost(${idx})" 
               style="background: rgba(30, 41, 59, 0.7); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 12px; cursor: pointer; transition: all 0.2s;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: 700; color: #38bdf8; font-size: 0.82rem;">Mục #${idx + 1}</span>
              ${p.permalink_url ? `<a href="${p.permalink_url}" target="_blank" onclick="event.stopPropagation()" style="font-size: 0.72rem; color: #94a3b8;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Mở FB</a>` : ''}
            </div>
            <div style="font-weight: 600; font-size: 0.85rem; color: #fff; line-height: 1.35; margin-bottom: 8px; height: 38px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
              ${escapeHtml(p.mo_ta || p.post_id)}
            </div>
            <div style="display: flex; gap: 6px; font-size: 0.75rem; flex-wrap: wrap;">
              <span style="color: #f87171; background: rgba(239, 68, 68, 0.15); padding: 1px 6px; border-radius: 4px; font-weight: 600;">❤️ ${p.likes_count}</span>
              <span style="color: #38bdf8; background: rgba(56, 189, 248, 0.15); padding: 1px 6px; border-radius: 4px; font-weight: 600;">💬 ${p.comments_count}</span>
              <span style="color: #fbbf24; background: rgba(245, 158, 11, 0.15); padding: 1px 6px; border-radius: 4px; font-weight: 600;">🔁 ${p.shares_count}</span>
            </div>
          </div>
        `;
      });
      cardsContainer.innerHTML = cardsHtml;
    }
  }

  // Tự động chọn bài đầu tiên cho Tab 2
  if (allPostsDetails.length > 0) {
    selectInspectorPost(0);
  }

  // Mặc định chuyển sang Tab 1: Danh Sách Tên Người Tương Tác
  switchResultTab('users');

  // 4. Render Tab Đối soát Thành viên (nếu có)
  const memBody = document.getElementById('table-members-body');
  if (memBody && data.match_results) {
    if (data.match_results.length === 0) {
      memBody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 20px; color: var(--text-muted);">Không có thành viên nào (Chưa nạp file Excel thành viên)</td></tr>';
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

  // 4. Render Tab Người ngoài nhóm
  const strBody = document.getElementById('table-strangers-body');
  if (strBody && data.strangers) {
    if (data.strangers.length === 0) {
      strBody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: var(--text-muted);">Không phát hiện người ngoài nhóm hoặc chưa nạp danh sách thành viên</td></tr>';
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

  // 5. Render Tab Tổng hợp bài viết
  const postBody = document.getElementById('table-posts-body');
  if (postBody && data.post_summary) {
    let html = '';
    data.post_summary.forEach((p, pIdx) => {
      html += `
        <tr style="border-bottom: 1px solid var(--border-subtle);">
          <td style="padding: 10px 14px; font-weight: 600; color: #38bdf8; font-family: var(--font-mono);">#${p.post_id}</td>
          <td style="padding: 10px 14px;">
            <div style="font-weight: 600; color: #fff;">${escapeHtml(p.mo_ta || p.post_id)}</div>
            ${p.permalink_url ? `<a href="${p.permalink_url}" target="_blank" style="color: #38bdf8; font-size: 0.78rem;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Mở bài viết trên Facebook</a>` : ''}
          </td>
          <td style="padding: 10px 14px; text-align: center; color: #ef4444; font-weight: 700;">❤️ ${p.likes_count}</td>
          <td style="padding: 10px 14px; text-align: center; color: #38bdf8; font-weight: 700;">💬 ${p.comments_count}</td>
          <td style="padding: 10px 14px; text-align: center; color: #f59e0b; font-weight: 700;">🔁 ${p.shares_count}</td>
          <td style="padding: 10px 14px; text-align: center;">
            <button type="button" class="btn btn-sm btn-secondary" onclick="selectInspectorPost(${pIdx}); switchResultTab('inspector');" style="border-color: #38bdf8; color: #38bdf8; font-size: 0.75rem;">
              <i class="fa-solid fa-eye"></i> Xem người tương tác
            </button>
          </td>
        </tr>
      `;
    });
    postBody.innerHTML = html;
  }
}

// =========================================================================
// BẢNG TỔNG HỢP DANH SÁCH TẤT CẢ TÊN NGƯỜI DÙNG TƯƠNG TÁC TOÀN TRANG (TAB 1)
// =========================================================================
function renderUsersDirectoryTable(searchQuery = '') {
  const tableBody = document.getElementById('table-users-body');
  if (!tableBody) return;

  let list = allUsersDirectory || [];

  // Lọc theo loại tương tác
  if (currentUserFilterType === 'like') {
    list = list.filter(u => u.likes_count > 0);
  } else if (currentUserFilterType === 'comment') {
    list = list.filter(u => u.comments_count > 0);
  } else if (currentUserFilterType === 'share') {
    list = list.filter(u => u.shares_count > 0);
  }

  // Lọc theo ô tìm kiếm
  const q = (searchQuery || '').toLowerCase().trim();
  if (q) {
    list = list.filter(u => 
      (u.name || '').toLowerCase().includes(q) ||
      (u.user_id || '').toLowerCase().includes(q)
    );
  }

  if (list.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 24px; color: var(--text-muted);">Không tìm thấy người dùng nào ${currentUserFilterType !== 'all' ? `phù hợp với bộ lọc` : ''}.</td></tr>`;
    return;
  }

  let html = '';
  list.forEach((u, idx) => {
    const initial = (u.name[0] || 'U').toUpperCase();
    const rate = u.participation_rate || 0;
    let rateColor = '#34d399';
    if (rate < 30) rateColor = '#f87171';
    else if (rate < 70) rateColor = '#fbbf24';

    html += `
      <tr style="border-bottom: 1px solid var(--border-subtle);">
        <td style="padding: 10px 14px; color: var(--text-muted); font-family: var(--font-mono);">${idx + 1}</td>
        <td style="padding: 10px 14px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <div style="width: 28px; height: 28px; border-radius: 50%; background: linear-gradient(135deg, #38bdf8, #2563eb); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 0.78rem; font-weight: 700;">
              ${initial}
            </div>
            <div>
              ${u.profile_url ? `<a href="${u.profile_url}" target="_blank" style="font-weight: 700; color: #fff; font-size: 0.88rem;">${escapeHtml(u.name)}</a>` : `<span style="font-weight: 700; color: #fff;">${escapeHtml(u.name)}</span>`}
            </div>
          </div>
        </td>
        <td style="padding: 10px 14px; font-family: var(--font-mono); font-size: 0.8rem; color: #93c5fd;">
          ${u.user_id ? escapeHtml(u.user_id) : '<span style="color: var(--text-muted);">-</span>'}
        </td>
        <td style="padding: 10px 14px; text-align: center;">
          ${u.likes_count > 0 ? `<span style="background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); padding: 2px 8px; border-radius: 9999px; font-weight: 700; font-size: 0.8rem;" title="${u.liked_posts.length} bài">❤️ ${u.likes_count} bài</span>` : '<span style="color: #64748b;">-</span>'}
        </td>
        <td style="padding: 10px 14px; text-align: center;">
          ${u.comments_count > 0 ? `<span style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 2px 8px; border-radius: 9999px; font-weight: 700; font-size: 0.8rem;" title="${escapeHtml((u.commented_posts[0] || {}).message || '')}">💬 ${u.comments_count} cmt</span>` : '<span style="color: #64748b;">-</span>'}
        </td>
        <td style="padding: 10px 14px; text-align: center;">
          ${u.shares_count > 0 ? `<span style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); padding: 2px 8px; border-radius: 9999px; font-weight: 700; font-size: 0.8rem;">🔁 ${u.shares_count} bài</span>` : '<span style="color: #64748b;">-</span>'}
        </td>
        <td style="padding: 10px 14px; text-align: center; font-weight: 800; font-size: 0.95rem; color: #fff;">
          ${u.total_interactions}
        </td>
        <td style="padding: 10px 14px; text-align: center;">
          <div style="font-weight: 700; color: ${rateColor}; font-size: 0.85rem;">${rate}%</div>
          <div style="font-size: 0.72rem; color: var(--text-muted);">${u.distinct_posts_count}/${trackingData ? trackingData.total_posts : 0} bài</div>
          <div style="width: 100%; background: rgba(255,255,255,0.08); height: 5px; border-radius: 3px; margin-top: 3px; overflow: hidden;">
            <div style="width: ${rate}%; background: ${rateColor}; height: 100%;"></div>
          </div>
        </td>
      </tr>
    `;
  });

  tableBody.innerHTML = html;
}

function filterUsersDirectory(type) {
  currentUserFilterType = type;
  const btnAll = document.getElementById('btn-user-filter-all');
  const btnLike = document.getElementById('btn-user-filter-like');
  const btnComment = document.getElementById('btn-user-filter-comment');
  const btnShare = document.getElementById('btn-user-filter-share');

  [btnAll, btnLike, btnComment, btnShare].forEach(b => {
    if (b) b.className = 'btn btn-sm btn-secondary';
  });
  if (type === 'all' && btnAll) btnAll.className = 'btn btn-sm btn-primary';
  if (type === 'like' && btnLike) btnLike.className = 'btn btn-sm btn-primary';
  if (type === 'comment' && btnComment) btnComment.className = 'btn btn-sm btn-primary';
  if (type === 'share' && btnShare) btnShare.className = 'btn btn-sm btn-primary';

  const searchInput = document.getElementById('input-search-users');
  const query = searchInput ? searchInput.value : '';
  renderUsersDirectoryTable(query);
}

function searchUsersDirectory(query) {
  renderUsersDirectoryTable(query);
}

// Bấm chọn xem tương tác của một bài viết cụ thể
function selectInspectorPost(index) {
  if (!allPostsDetails || index < 0 || index >= allPostsDetails.length) return;
  currentSelectedPostIndex = index;

  // Highlight card
  document.querySelectorAll('.post-item-card').forEach((c, idx) => {
    if (idx === index) {
      c.style.border = '2px solid #38bdf8';
      c.style.background = 'rgba(56, 189, 248, 0.12)';
    } else {
      c.style.border = '1px solid var(--border-subtle)';
      c.style.background = 'rgba(30, 41, 59, 0.7)';
    }
  });

  const post = allPostsDetails[index];
  document.getElementById('active-post-badge').innerText = `MỤC #${index + 1} (POST ID: ${post.post_id})`;
  document.getElementById('active-post-title').innerText = post.mo_ta || `Bài viết ID ${post.post_id}`;

  const linkBox = document.getElementById('active-post-link-container');
  if (linkBox) {
    if (post.permalink_url) {
      linkBox.innerHTML = `<a href="${post.permalink_url}" target="_blank" style="color: #38bdf8; font-size: 0.8rem;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Mở bài viết gốc trên Facebook</a>`;
    } else {
      linkBox.innerHTML = '';
    }
  }

  // Cập nhật số đếm
  document.getElementById('active-cnt-like').innerText = post.likes_count || 0;
  document.getElementById('active-cnt-comment').innerText = post.comments_count || 0;
  document.getElementById('active-cnt-share').innerText = post.shares_count || 0;

  const totalInteractions = (post.likes_count || 0) + (post.comments_count || 0) + (post.shares_count || 0);
  document.getElementById('filter-cnt-all').innerText = totalInteractions;
  document.getElementById('filter-cnt-like').innerText = post.likes_count || 0;
  document.getElementById('filter-cnt-comment').innerText = post.comments_count || 0;
  document.getElementById('filter-cnt-share').innerText = post.shares_count || 0;

  // Reset filter và search
  currentPostFilterType = 'all';
  updateFilterButtonsUI('all');
  const searchInput = document.getElementById('input-search-post-interactions');
  if (searchInput) searchInput.value = '';

  renderCurrentPostTable();
}

// Render bảng danh sách người thả tim, comment, share của bài đang chọn
function renderCurrentPostTable(searchQuery = '') {
  const tableBody = document.getElementById('table-inspector-body');
  if (!tableBody || !allPostsDetails[currentSelectedPostIndex]) return;

  const post = allPostsDetails[currentSelectedPostIndex];
  const list = [];

  // 1. Thêm lượt Like
  if (post.reactions && Array.isArray(post.reactions)) {
    post.reactions.forEach(r => {
      list.push({
        type: 'like',
        typeLabel: `Thả tim (${r.type || 'LIKE'})`,
        typeColor: '#ef4444',
        typeBg: 'rgba(239, 68, 68, 0.15)',
        name: r.name || 'Người dùng Facebook',
        id: r.id || r.user_id || '',
        url: r.profile_url || (r.id ? `https://facebook.com/${r.id}` : ''),
        detail: `Thả cảm xúc ${r.type || 'LIKE'}`,
        time: '-'
      });
    });
  }

  // 2. Thêm bình luận
  if (post.comments && Array.isArray(post.comments)) {
    post.comments.forEach(c => {
      const cId = c.from_id || c.id || '';
      list.push({
        type: 'comment',
        typeLabel: 'Bình luận',
        typeColor: '#38bdf8',
        typeBg: 'rgba(56, 189, 248, 0.15)',
        name: c.from_name || c.name || 'Người dùng Facebook',
        id: cId,
        url: cId ? `https://facebook.com/${cId}` : '',
        detail: c.message || '(Không có nội dung chữ)',
        time: c.created_time || '-'
      });
    });
  }

  // 3. Thêm lượt chia sẻ
  if (post.shares && Array.isArray(post.shares)) {
    post.shares.forEach(s => {
      const sId = s.id || s.user_id || '';
      list.push({
        type: 'share',
        typeLabel: 'Chia sẻ',
        typeColor: '#fbbf24',
        typeBg: 'rgba(245, 158, 11, 0.15)',
        name: s.name || 'Người dùng Facebook',
        id: sId,
        url: sId ? `https://facebook.com/${sId}` : '',
        detail: 'Chia sẻ bài viết công khai',
        time: '-'
      });
    });
  }

  // Áp dụng bộ lọc loại tương tác
  let filtered = list;
  if (currentPostFilterType !== 'all') {
    filtered = filtered.filter(item => item.type === currentPostFilterType);
  }

  // Áp dụng bộ lọc tìm kiếm
  const q = (searchQuery || '').toLowerCase().trim();
  if (q) {
    filtered = filtered.filter(item => 
      item.name.toLowerCase().includes(q) || 
      item.id.toLowerCase().includes(q) || 
      item.detail.toLowerCase().includes(q)
    );
  }

  if (filtered.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 24px; color: var(--text-muted);">Không tìm thấy người tương tác nào ${currentPostFilterType !== 'all' ? `cho mục này` : ''}</td></tr>`;
    return;
  }

  let html = '';
  filtered.forEach((item, idx) => {
    const initial = (item.name[0] || 'U').toUpperCase();
    html += `
      <tr style="border-bottom: 1px solid var(--border-subtle);">
        <td style="padding: 10px 14px; color: var(--text-muted); font-family: var(--font-mono);">${idx + 1}</td>
        <td style="padding: 10px 14px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <div style="width: 24px; height: 24px; border-radius: 50%; background: ${item.typeColor}; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 700;">
              ${initial}
            </div>
            <div>
              ${item.url ? `<a href="${item.url}" target="_blank" style="font-weight: 700; color: #fff; font-size: 0.88rem;">${escapeHtml(item.name)}</a>` : `<span style="font-weight: 700; color: #fff;">${escapeHtml(item.name)}</span>`}
            </div>
          </div>
        </td>
        <td style="padding: 10px 14px; font-family: var(--font-mono); font-size: 0.8rem; color: #93c5fd;">
          ${item.id ? escapeHtml(item.id) : '<span style="color: var(--text-muted);">-</span>'}
        </td>
        <td style="padding: 10px 14px; text-align: center;">
          <span style="background: ${item.typeBg}; color: ${item.typeColor}; border: 1px solid ${item.typeColor}40; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600;">
            ${escapeHtml(item.typeLabel)}
          </span>
        </td>
        <td style="padding: 10px 14px; color: #e2e8f0; font-size: 0.82rem; max-width: 320px; line-height: 1.4;">
          ${escapeHtml(item.detail)}
        </td>
        <td style="padding: 10px 14px; color: var(--text-muted); font-size: 0.78rem;">${escapeHtml(item.time)}</td>
      </tr>
    `;
  });

  tableBody.innerHTML = html;
}

function filterCurrentPostInteractions(type) {
  currentPostFilterType = type;
  updateFilterButtonsUI(type);
  const searchInput = document.getElementById('input-search-post-interactions');
  const query = searchInput ? searchInput.value : '';
  renderCurrentPostTable(query);
}

function updateFilterButtonsUI(activeType) {
  const btnAll = document.getElementById('btn-post-filter-all');
  const btnLike = document.getElementById('btn-post-filter-like');
  const btnComment = document.getElementById('btn-post-filter-comment');
  const btnShare = document.getElementById('btn-post-filter-share');

  [btnAll, btnLike, btnComment, btnShare].forEach(b => {
    if (b) b.className = 'btn btn-sm btn-secondary';
  });

  if (activeType === 'all' && btnAll) btnAll.className = 'btn btn-sm btn-primary';
  if (activeType === 'like' && btnLike) btnLike.className = 'btn btn-sm btn-primary';
  if (activeType === 'comment' && btnComment) btnComment.className = 'btn btn-sm btn-primary';
  if (activeType === 'share' && btnShare) btnShare.className = 'btn btn-sm btn-primary';
}

function searchCurrentPostInteractions(query) {
  renderCurrentPostTable(query);
}

function switchResultTab(tabName) {
  const tabUsers = document.getElementById('tab-view-users');
  const tabInspector = document.getElementById('tab-view-inspector');
  const tabMembers = document.getElementById('tab-view-members');
  const tabPosts = document.getElementById('tab-view-posts');

  const btnUsers = document.getElementById('tab-btn-users');
  const btnInspector = document.getElementById('tab-btn-inspector');
  const btnMembers = document.getElementById('tab-btn-members');
  const btnPosts = document.getElementById('tab-btn-posts');

  [tabUsers, tabInspector, tabMembers, tabPosts].forEach(t => {
    if (t) t.style.display = 'none';
  });
  [btnUsers, btnInspector, btnMembers, btnPosts].forEach(b => {
    if (b) b.className = 'btn btn-sm btn-secondary';
  });

  if (tabName === 'users' && tabUsers) {
    tabUsers.style.display = 'block';
    if (btnUsers) btnUsers.className = 'btn btn-sm btn-primary';
  } else if (tabName === 'inspector' && tabInspector) {
    tabInspector.style.display = 'block';
    if (btnInspector) btnInspector.className = 'btn btn-sm btn-primary';
  } else if (tabName === 'members' && tabMembers) {
    tabMembers.style.display = 'block';
    if (btnMembers) btnMembers.className = 'btn btn-sm btn-primary';
  } else if (tabName === 'posts' && tabPosts) {
    tabPosts.style.display = 'block';
    if (btnPosts) btnPosts.className = 'btn btn-sm btn-primary';
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

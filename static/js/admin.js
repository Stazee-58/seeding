// ==========================================================================
// FB TRACKING NO-API — ADMIN JAVASCRIPT
// ==========================================================================

async function toggleUserActive(userId, currentActive) {
  const newActive = currentActive === 1 ? 0 : 1;
  const actionText = newActive === 1 ? 'kích hoạt' : 'khóa';

  if (!confirm(`Bạn có chắc chắn muốn ${actionText} tài khoản này không?`)) {
    return;
  }

  try {
    const res = await fetch('/api/admin/toggle-active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, is_active: newActive })
    });
    const data = await res.json();
    if (data.success) {
      location.reload();
    } else {
      alert('Lỗi: ' + (data.error || 'Không thể thực hiện'));
    }
  } catch (err) {
    alert('Lỗi kết nối máy chủ: ' + err);
  }
}

async function deleteUser(userId, email) {
  if (!confirm(`⚠️ CẢNH BÁO: Bạn có chắc chắn muốn XÓA vĩnh viễn tài khoản: ${email}?`)) {
    return;
  }

  try {
    const res = await fetch('/api/admin/delete-user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId })
    });
    const data = await res.json();
    if (data.success) {
      const row = document.getElementById(`row-user-${userId}`);
      if (row) row.remove();
      location.reload();
    } else {
      alert('Lỗi: ' + (data.error || 'Không thể xóa'));
    }
  } catch (err) {
    alert('Lỗi kết nối máy chủ: ' + err);
  }
}

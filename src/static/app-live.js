const appView = document.querySelector('#app-view');
const title = document.querySelector('#page-title');
const breadcrumb = document.querySelector('#breadcrumb-title');
const sidebar = document.querySelector('.sidebar');
const drawerBackdrop = document.querySelector('.drawer-backdrop');
const API_URL = '';
let currentView = 'overview';
let orders = [];
let riders = [];
let activity = [];
let operator = null;

const icon = name => `<i data-lucide="${name}"></i>`;
const renderIcons = () => window.lucide && window.lucide.createIcons();
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[character]));
const showToast = message => {
  const toast = document.querySelector('#toast');
  toast.querySelector('span').textContent = message;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 2600);
};
const api = async (path, options = {}) => {
  const response = await fetch(`${API_URL}${path}`, {
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
};
const updateOperatorUi = () => {
  document.querySelector('#profile-name').textContent = operator.display_name;
  document.querySelector('#profile-initials').textContent = operator.initials;
};
const requireSession = async () => {
  const saved = window.sessionStorage.getItem('reflex.operator');
  if (saved) {
    operator = JSON.parse(saved);
    updateOperatorUi();
    return;
  }
  const gate = document.querySelector('#session-gate');
  gate.setAttribute('aria-hidden', 'false');
  renderIcons();
  await new Promise(resolve => {
    document.querySelector('#session-form').addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.target.querySelector('button');
      button.disabled = true;
      try {
        operator = await api('/session', {method: 'POST', body: JSON.stringify({name: document.querySelector('#session-name').value})});
        window.sessionStorage.setItem('reflex.operator', JSON.stringify(operator));
        updateOperatorUi();
        gate.remove();
        resolve();
      } catch (error) {
        button.disabled = false;
        showToast(error.message);
      }
    }, {once: true});
  });
};
const displayStatus = {logged: 'Logged', assigned: 'Assigned', picked_up: 'Picked Up', en_route: 'En Route', delivered: 'Delivered'};
const apiStatus = {'Picked Up': 'picked_up', 'En Route': 'en_route', Delivered: 'delivered'};
const orderId = order => `RX-${String(1000 + (order.order_id ?? order.id)).padStart(4, '0')}`;
const normalizeOrder = order => ({...order, order_id: order.order_id ?? order.id, id: orderId(order), customer: order.customer_name || 'Customer', rider: order.rider_name || order.rider_id || 'Unassigned', item: order.item_description, address: order.delivery_address || order.address, status: displayStatus[order.status] || order.status});
const statusClass = status => status === 'Delivered' ? 'status-delivered' : status === 'Logged' ? 'status-logged' : status === 'Assigned' ? 'status-assigned' : 'status-progress';
const loadData = async () => {
  const [loadedOrders, loadedRiders, loadedActivity] = await Promise.all([api('/orders'), api('/riders'), api('/activity')]);
  orders = loadedOrders.map(normalizeOrder);
  riders = loadedRiders;
  activity = loadedActivity;
};
const refresh = async rerender => {
  try {
    await loadData();
    if (rerender) render();
    const sync = document.querySelector('.sync-status small');
    if (sync) sync.textContent = `Updated ${new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
  } catch (error) {
    showToast(`Could not sync with the API: ${error.message}`);
  }
};
const orderRows = list => list.map(order => `<div class="order-row"><div><b class="order-number">${escapeHtml(order.id)}</b><div class="address">${escapeHtml(order.item)}</div></div><div><b class="customer">${escapeHtml(order.customer)}</b><div class="address">${escapeHtml(order.address)}</div></div><div><span class="status ${statusClass(order.status)}">${escapeHtml(order.status)}</span></div><div class="order-meta">${escapeHtml(order.rider)}</div><button class="mini-action" aria-label="Open ${escapeHtml(order.id)}" data-order="${order.id}">${icon('arrow-up-right')}</button></div>`).join('');
const renderOverview = () => {
  const active = orders.filter(order => order.status !== 'Delivered' && order.status !== 'Logged').length;
  const pending = orders.filter(order => order.status === 'Logged').length;
  const completed = orders.filter(order => order.status === 'Delivered').length;
  const available = riders.filter(rider => rider.status === 'available').length;
  return `<div class="metrics-grid"><div class="metric-card"><div class="metric-top"><span>Active deliveries</span><span class="metric-icon icon-mint">${icon('route')}</span></div><div class="metric-value">${String(active).padStart(2, '0')}</div></div><div class="metric-card"><div class="metric-top"><span>Awaiting dispatch</span><span class="metric-icon icon-amber">${icon('timer')}</span></div><div class="metric-value">${String(pending).padStart(2, '0')}</div></div><div class="metric-card"><div class="metric-top"><span>Completed deliveries</span><span class="metric-icon icon-blue">${icon('package-check')}</span></div><div class="metric-value">${String(completed).padStart(2, '0')}</div></div><div class="metric-card"><div class="metric-top"><span>Available riders</span><span class="metric-icon icon-coral">${icon('bike')}</span></div><div class="metric-value">${String(available).padStart(2, '0')}</div></div></div><div class="dashboard-grid"><section class="panel"><div class="panel-head"><div><h2>Live delivery board</h2><p>Persisted delivery state from SQLite</p></div><button class="text-button" data-view="orders">View all ${icon('arrow-up-right')}</button></div>${orderRows(orders.slice(0, 5)) || '<div class="empty-state"><p>No delivery requests yet.</p></div>'}</section><section class="panel"><div class="panel-head"><div><h2>Recent activity</h2><p>Persisted order transitions</p></div>${icon('activity')}</div>${renderActivityItems(activity.slice(0, 5))}</section></div>`;
};
const renderActivityItems = logs => logs.length ? `<div class="activity-list">${logs.map(log => `<div class="activity-item"><span class="activity-icon">${icon(log.new_status === 'Delivered' ? 'check-circle-2' : 'activity')}</span><div class="activity-copy"><b>Order #${log.order_id} moved to ${escapeHtml(log.new_status)}</b><small>${escapeHtml(log.triggered_by)} · ${escapeHtml(log.timestamp)}</small></div></div>`).join('')}</div>` : '<div class="empty-state"><p>No activity recorded yet.</p></div>';
const renderOrders = () => `<div class="view-toolbar"><div class="search-box">${icon('search')}<input id="order-search" placeholder="Search order or customer" /></div><span class="status status-progress">${orders.length} persisted requests</span></div><section class="panel view-panel"><div class="panel-head"><div><h2>All deliveries</h2><p>Live records from the database</p></div></div>${orderRows(orders)}</section>`;
const renderDispatch = () => {
  const pending = orders.filter(order => order.status === 'Logged');
  const available = riders.filter(rider => rider.status === 'available');
  return `<div class="view-toolbar"><div class="search-box">${icon('search')}<input placeholder="Search unassigned requests" /></div><span class="status status-logged">${pending.length} need attention</span></div><section class="panel view-panel"><div class="panel-head"><div><h2>Dispatch queue</h2><p>Assign persisted requests to available riders</p></div><span class="status status-progress">${available.length} riders available</span></div><div class="queue-grid">${pending.map(order => `<article class="queue-card"><div class="queue-card-head"><div><h3>${escapeHtml(order.id)}</h3><p>${escapeHtml(order.customer)}</p></div><span class="status status-logged">Logged</span></div><div class="queue-divider"></div><div class="queue-detail">${icon('map-pin')} ${escapeHtml(order.address)}</div><div class="queue-detail">${icon('package')} ${escapeHtml(order.item)}</div><div class="assign-row"><select aria-label="Assign rider for ${order.id}" data-rider-select="${order.order_id}"><option value="">Choose a rider</option>${available.map(rider => `<option value="${rider.rider_id}">${escapeHtml(rider.name)}</option>`).join('')}</select><button class="assign-button" data-assign-order="${order.order_id}">Assign ${icon('arrow-right')}</button></div></article>`).join('') || '<div class="empty-state"><div>' + icon('check-circle-2') + '</div><p>All requests are assigned.</p></div>'}</div></section>`;
};
const nextStatus = {Assigned: 'Picked Up', 'Picked Up': 'En Route', 'En Route': 'Delivered'};
const renderRiderActions = () => {
  const assigned = orders.filter(order => order.assigned_rider_id && order.status !== 'Delivered');
  return `<div class="rider-context"><div class="rider-card-head"><span class="rider-avatar">${escapeHtml(riders[0]?.initials || 'R')}</span><div><h3>Active rider jobs</h3><small>${assigned.length} persisted jobs</small></div></div><span class="status status-progress">Live route</span></div><section class="panel view-panel"><div class="panel-head"><div><h2>Today’s deliveries</h2><p>Advance the persisted order workflow</p></div></div><div class="rider-action-list">${assigned.map(order => `<article class="rider-job"><div class="job-top"><div><b class="order-number">${escapeHtml(order.id)}</b><h3>${escapeHtml(order.customer)}</h3><p>${escapeHtml(order.address)}</p></div><span class="status ${statusClass(order.status)}">${escapeHtml(order.status)}</span></div><div class="job-item">${icon('package')} ${escapeHtml(order.item)} · ${escapeHtml(order.rider)}</div><div class="job-actions"><button class="primary-button status-action" data-status-order="${order.order_id}">${nextStatus[order.status] || 'Complete'} ${icon('arrow-right')}</button></div></article>`).join('') || '<div class="empty-state"><p>No active rider jobs.</p></div>'}</div></section>`;
};
const renderRiders = () => `<section class="panel view-panel"><div class="panel-head"><div><h2>Rider team</h2><p>Manage riders stored in SQLite</p></div><button class="text-button" data-action="new-rider">Add rider ${icon('plus')}</button></div><div class="rider-grid">${riders.map(rider => `<div class="rider-card"><div class="rider-card-head"><span class="rider-avatar">${escapeHtml(rider.initials)}</span><div><h3>${escapeHtml(rider.name)}</h3><small>${escapeHtml(rider.vehicle_type || 'Vehicle not set')}</small></div></div><div class="rider-status ${rider.status === 'available' ? '' : 'offline'}">${escapeHtml(rider.status.replace('_', ' '))}</div><div class="rider-stat"><b>${rider.jobs_today}</b> active jobs</div><button class="secondary-button rider-toggle" data-rider-id="${rider.rider_id}" data-next-status="${rider.status === 'offline' ? 'available' : 'offline'}">Set ${rider.status === 'offline' ? 'available' : 'offline'}</button></div>`).join('') || '<div class="empty-state"><p>No riders have been created yet.</p></div>'}</div><div id="rider-form"></div></section>`;
const renderRiderForm = () => { const form = document.querySelector('#rider-form'); if (form) form.innerHTML = `<form id="new-rider-form" class="form-panel"><h3>Add a rider</h3><div class="form-grid"><div class="field"><label for="rider-first-name">First name</label><input id="rider-first-name" required /></div><div class="field"><label for="rider-last-name">Last name</label><input id="rider-last-name" required /></div><div class="field"><label for="rider-phone">Phone number</label><input id="rider-phone" required /></div><div class="field"><label for="rider-vehicle">Vehicle type</label><input id="rider-vehicle" placeholder="Motorbike" /></div></div><div class="form-actions"><button type="button" class="secondary-button" data-action="cancel-rider">Cancel</button><button class="primary-button" type="submit">Create rider ${icon('arrow-right')}</button></div></form>`; renderIcons(); };
const renderNewOrder = () => `<div class="form-layout"><section class="panel form-panel"><h2>Log a new delivery</h2><p>Capture a request that will be stored in SQLite.</p><form id="new-order-form"><div class="form-grid"><div class="field"><label for="customer-name">Customer name</label><input id="customer-name" required /></div><div class="field"><label for="customer-phone">Phone number</label><input id="customer-phone" required /></div><div class="field full"><label for="delivery-address">Delivery address</label><input id="delivery-address" required /></div><div class="field full"><label for="item-description">Item description</label><textarea id="item-description" required></textarea></div></div><div class="form-actions"><button type="button" class="secondary-button" data-view="overview">Cancel</button><button class="primary-button" type="submit">Create request ${icon('arrow-right')}</button></div></form></section></div>`;
const renderActivity = () => `<section class="panel"><div class="panel-head"><div><h2>Activity log</h2><p>Audit events read from the database</p></div></div>${renderActivityItems(activity)}</section>`;
const render = () => {
  const config = {overview: ['Overview', `Good morning, ${operator.first_name}`], orders: ['All deliveries', 'Delivery board'], 'new-order': ['New request', 'Create a delivery request'], dispatch: ['Dispatcher queue', 'Dispatch with confidence'], 'rider-actions': ['Rider actions', 'Your next handoffs'], riders: ['Rider team', 'Your rider network'], activity: ['Activity log', 'Team activity']};
  const [crumb, heading] = config[currentView];
  breadcrumb.textContent = crumb;
  title.innerHTML = `${heading} <span>↗</span>`;
  appView.innerHTML = currentView === 'overview' ? renderOverview() : currentView === 'orders' ? renderOrders() : currentView === 'new-order' ? renderNewOrder() : currentView === 'dispatch' ? renderDispatch() : currentView === 'rider-actions' ? renderRiderActions() : currentView === 'riders' ? renderRiders() : renderActivity();
  document.querySelectorAll('[data-view]').forEach(element => element.onclick = () => { currentView = element.dataset.view; closeDrawer(); render(); });
  renderIcons();
};
const closeDrawer = () => { sidebar.classList.remove('open'); drawerBackdrop.classList.remove('visible'); };
document.querySelector('.mobile-menu').onclick = () => { sidebar.classList.toggle('open'); drawerBackdrop.classList.toggle('visible'); };
drawerBackdrop.onclick = closeDrawer;
document.addEventListener('click', async event => {
  const action = event.target.closest('[data-action]');
  if (action?.dataset.action === 'new-rider') return renderRiderForm();
  if (action?.dataset.action === 'cancel-rider') return render();
  const assign = event.target.closest('.assign-button');
  if (assign) {
    const riderId = document.querySelector(`[data-rider-select="${assign.dataset.assignOrder}"]`).value;
    if (!riderId) return showToast('Choose an available rider first');
    try { await api(`/orders/${assign.dataset.assignOrder}/assign`, {method: 'POST', body: JSON.stringify({assigned_rider_id: Number(riderId), assigned_by_user_id: operator.user_id})}); await refresh(true); showToast('Job assigned and saved'); } catch (error) { showToast(error.message); }
  }
  const statusButton = event.target.closest('[data-status-order]');
  if (statusButton) {
    const order = orders.find(item => item.order_id === Number(statusButton.dataset.statusOrder));
    try { await api(`/orders/${order.order_id}/status`, {method: 'PATCH', body: JSON.stringify({status: apiStatus[nextStatus[order.status]]})}); await refresh(true); showToast('Job status saved'); } catch (error) { showToast(error.message); }
  }
  const toggle = event.target.closest('.rider-toggle');
  if (toggle) {
    try { await api(`/riders/${toggle.dataset.riderId}/status`, {method: 'PATCH', body: JSON.stringify({status: toggle.dataset.nextStatus})}); await refresh(true); showToast('Rider availability saved'); } catch (error) { showToast(error.message); }
  }
});
document.addEventListener('submit', async event => {
  event.preventDefault();
  if (event.target.id === 'new-order-form') {
    try { await api('/orders', {method: 'POST', body: JSON.stringify({customer_name: document.querySelector('#customer-name').value, customer_phone: document.querySelector('#customer-phone').value, address: document.querySelector('#delivery-address').value, item_description: document.querySelector('#item-description').value})}); await refresh(false); currentView = 'dispatch'; render(); showToast('Request saved to the database'); } catch (error) { showToast(error.message); }
  }
  if (event.target.id === 'new-rider-form') {
    try { await api('/riders', {method: 'POST', body: JSON.stringify({first_name: document.querySelector('#rider-first-name').value, last_name: document.querySelector('#rider-last-name').value, phone_number: document.querySelector('#rider-phone').value, vehicle_type: document.querySelector('#rider-vehicle').value || null})}); await refresh(false); render(); showToast('Rider saved to the database'); } catch (error) { showToast(error.message); }
  }
});
requireSession().then(() => loadData()).then(render).catch(error => { showToast(`Could not connect to Reflex API: ${error.message}`); render(); });
window.setInterval(() => refresh(false), 10000);

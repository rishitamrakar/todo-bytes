// todo-bytes UI — vanilla JS, no build step.
//
// Organisation:
//   - state (one object, no globals scattered)
//   - api (thin wrappers around fetch)
//   - render (one function per UI region)
//   - actions (called from event handlers)
//   - boot (wire everything up on DOMContentLoaded)

// ---------- state ----------

const state = {
  lists: [],
  defaultList: null,
  activeList: null,
  activeView: 'open',
  tasks: [],
  editingTaskId: null,  // null = creating new task
};


// ---------- api ----------

const api = {
  async getLists() {
    return fetchJson('/api/lists');
  },
  async getTasks(listName, view) {
    const params = new URLSearchParams({ list: listName, view });
    return fetchJson(`/api/tasks?${params}`);
  },
  async createTask(payload) {
    return fetchJson('/api/tasks', { method: 'POST', body: payload });
  },
  async updateTask(listName, id, payload) {
    return fetchJson(`/api/tasks/${listName}/${id}`, { method: 'PATCH', body: payload });
  },
  async deleteTask(listName, id) {
    return fetchJson(`/api/tasks/${listName}/${id}`, { method: 'DELETE' });
  },
  async markDone(listName, id) {
    return fetchJson(`/api/tasks/${listName}/${id}/done`, { method: 'POST' });
  },
  async reopen(listName, id) {
    return fetchJson(`/api/tasks/${listName}/${id}/reopen`, { method: 'POST' });
  },
  async reorder(listName, ids) {
    return fetchJson(`/api/lists/${listName}/reorder`, { method: 'POST', body: { ids } });
  },
  async createList(name) {
    return fetchJson('/api/lists', { method: 'POST', body: { name } });
  },
};

async function fetchJson(url, opts = {}) {
  const { method = 'GET', body } = opts;
  const init = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) init.body = JSON.stringify(body);
  const res = await fetch(url, init);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}


// ---------- render: lists sidebar ----------

function renderLists() {
  const el = document.getElementById('lists');
  el.innerHTML = '';
  state.lists.forEach(l => el.appendChild(buildListItem(l)));
}

function buildListItem(listSummary) {
  const btn = document.createElement('button');
  btn.className = 'list-item' + (listSummary.name === state.activeList ? ' active' : '');
  btn.innerHTML = `
    <span>${escape(listSummary.name)}${listSummary.name === state.defaultList ? '<span class="default-mark">★</span>' : ''}</span>
    <span class="count">${listSummary.open}/${listSummary.total}</span>
  `;
  btn.addEventListener('click', () => switchList(listSummary.name));
  return btn;
}


// ---------- render: views tabs ----------

function renderViewTabs() {
  document.querySelectorAll('.view-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.view === state.activeView);
  });
  // Hint text + quick-add only relevant when looking at open tasks
  const isOpenView = state.activeView === 'open';
  document.getElementById('reorder-hint').hidden = !isOpenView;
  document.getElementById('quick-add').hidden = !isOpenView;
}


// ---------- render: tasks list ----------

function renderTasks() {
  const ul = document.getElementById('tasks');
  const empty = document.getElementById('empty-state');
  ul.innerHTML = '';
  if (state.tasks.length === 0) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  state.tasks.forEach(task => ul.appendChild(buildTaskRow(task)));
  if (state.activeView === 'open') {
    enableDragReorder(ul);
  }
}

function buildTaskRow(task) {
  const li = document.createElement('li');
  li.className = 'task ' + task.status;  // status used as a CSS modifier
  li.dataset.taskId = task.id;
  li.innerHTML = `
    <span class="drag-handle" title="Drag to reorder">⋮⋮</span>
    <button class="status-circle" data-action="toggle-done" title="${statusTitle(task.status)}"></button>
    <span class="task-name">${escape(task.name)}</span>
    <span class="due ${dueClass(task.due)}">${formatDue(task.due)}</span>
    <span class="tags">${(task.tags || []).map(t => `<span class="tag">${escape(t)}</span>`).join('')}</span>
    <span>${task.project ? `<span class="project">${escape(task.project)}</span>` : ''}</span>
    <span class="actions">
      <button class="icon-btn" data-action="edit" title="Edit">✎</button>
      <button class="icon-btn danger" data-action="delete" title="Delete">✕</button>
    </span>
  `;
  wireTaskRowEvents(li, task);
  return li;
}

function statusTitle(status) {
  const map = {
    'todo': 'Mark done',
    'in-progress': 'Mark done',
    'done': 'Click to un-do',
    'hold': 'On hold',
    'cancelled': 'Cancelled',
  };
  return map[status] || status;
}

function wireTaskRowEvents(li, task) {
  li.querySelector('.task-name').addEventListener('click', () => openEditModal(task));
  li.querySelector('.status-circle').addEventListener('click', e => {
    e.stopPropagation();
    toggleTaskDone(task);
  });
  li.querySelectorAll('.icon-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      handleTaskAction(btn.dataset.action, task);
    });
  });
}

function handleTaskAction(action, task) {
  if (action === 'edit') return openEditModal(task);
  if (action === 'delete') return deleteTask(task);
}


// ---------- drag-reorder ----------

function enableDragReorder(ul) {
  Sortable.create(ul, {
    handle: '.drag-handle',
    animation: 150,
    onEnd: () => persistNewOrder(ul),
  });
}

async function persistNewOrder(ul) {
  const ids = Array.from(ul.children).map(li => Number(li.dataset.taskId));
  try {
    await api.reorder(state.activeList, ids);
  } catch (err) {
    alert('Reorder failed: ' + err.message);
    await refreshTasks();
  }
}


// ---------- actions ----------

async function refreshLists() {
  const data = await api.getLists();
  state.lists = data.lists;
  state.defaultList = data.default;
  if (!state.activeList && state.lists.length > 0) {
    state.activeList = state.defaultList || state.lists[0].name;
  }
  renderLists();
  updateListTitle();
  renderStats();
}

async function refreshTasks() {
  if (!state.activeList) return;
  const data = await api.getTasks(state.activeList, state.activeView);
  state.tasks = data.tasks;
  renderTasks();
}

function switchList(name) {
  state.activeList = name;
  renderLists();
  updateListTitle();
  refreshTasks();
}

function switchView(view) {
  state.activeView = view;
  renderViewTabs();
  refreshTasks();
}

function updateListTitle() {
  document.getElementById('list-title').textContent = state.activeList || '—';
}

async function toggleTaskDone(task) {
  // Click the circle: done ↔ todo. Other statuses (hold, cancelled) need the modal.
  if (task.status === 'done') {
    await api.reopen(state.activeList, task.id);
  } else if (task.status === 'todo' || task.status === 'in-progress') {
    await api.markDone(state.activeList, task.id);
  } else {
    return;  // hold, cancelled — use edit modal
  }
  await refreshLists();
  await refreshTasks();
}

async function deleteTask(task) {
  if (!confirm(`Delete "${task.name}"?`)) return;
  await api.deleteTask(state.activeList, task.id);
  await refreshLists();
  await refreshTasks();
}


// ---------- inline quick-add ----------

async function handleQuickAddSubmit(event) {
  event.preventDefault();
  const input = document.getElementById('quick-add-input');
  const name = input.value.trim();
  if (!name) return;
  if (!state.activeList) {
    alert('Pick a list first.');
    return;
  }
  try {
    await api.createTask({ list: state.activeList, name });
  } catch (err) {
    alert('Add failed: ' + err.message);
    return;
  }
  input.value = '';
  await refreshLists();
  await refreshTasks();
  input.focus();  // ready for the next task
}


// ---------- modal: edit task ----------

function openEditModal(task) {
  state.editingTaskId = task.id;
  document.getElementById('modal-title').textContent = 'Edit task';
  fillTaskForm(task);
  showModal('task-modal');
}

function fillTaskForm(task) {
  const form = document.getElementById('task-form');
  form.elements.name.value = task.name || '';
  form.elements.due.value = isoToDatetimeLocal(task.due);
  form.elements.tags.value = (task.tags || []).join(', ');
  form.elements.project.value = task.project || '';
  form.elements.status.value = task.status || 'todo';
  document.getElementById('meta-created').textContent = task.created || '—';
}

async function submitTaskForm(event) {
  event.preventDefault();
  if (state.editingTaskId === null) return;  // edit-only modal
  const payload = readTaskForm(event.target);
  try {
    await api.updateTask(state.activeList, state.editingTaskId, payload);
  } catch (err) {
    alert('Save failed: ' + err.message);
    return;
  }
  hideModal('task-modal');
  await refreshLists();
  await refreshTasks();
}

function readTaskForm(form) {
  const tags = form.elements.tags.value
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  return {
    name: form.elements.name.value.trim(),
    due: datetimeLocalToIso(form.elements.due.value),
    tags,
    project: form.elements.project.value.trim() || null,
    status: form.elements.status.value,
  };
}


// ---------- modal: new list ----------

function openNewListModal() {
  document.getElementById('list-form').reset();
  showModal('list-modal');
}

async function submitListForm(event) {
  event.preventDefault();
  const name = event.target.elements.name.value.trim();
  if (!name) return;
  try {
    await api.createList(name);
  } catch (err) {
    alert('Create list failed: ' + err.message);
    return;
  }
  hideModal('list-modal');
  state.activeList = name;
  await refreshLists();
  await refreshTasks();
}


// ---------- modal helpers ----------

function showModal(id) { document.getElementById(id).hidden = false; }
function hideModal(id) { document.getElementById(id).hidden = true; }


// ---------- utils ----------

function escape(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// `due` arrives from the server as an ISO datetime string (e.g. 2026-05-10T23:59:59).
// If the time is end-of-day (23:59), show just the date — cleaner. Otherwise show date + time.
function formatDue(iso) {
  if (!iso) return '';
  const datePart = iso.slice(0, 10);
  const timePart = iso.slice(11, 16);  // HH:MM
  if (timePart === '23:59') return datePart;
  return `${datePart} ${timePart}`;
}

function dueClass(iso) {
  if (!iso) return '';
  const datePart = iso.slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);
  if (datePart < today) return 'overdue';
  if (datePart === today) return 'today';
  return '';
}

// <input type="datetime-local"> needs format YYYY-MM-DDTHH:MM (no seconds).
function isoToDatetimeLocal(iso) {
  if (!iso) return '';
  return iso.slice(0, 16);
}

function datetimeLocalToIso(localValue) {
  // The browser gives us YYYY-MM-DDTHH:MM (or empty). Server accepts either.
  return localValue || null;
}

// Update the stats card in the side pane based on the current list summary.
function renderStats() {
  const summary = state.lists.find(l => l.name === state.activeList);
  const open = summary ? summary.open : 0;
  const done = summary ? summary.done : 0;
  const total = open + done;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  document.getElementById('stat-open').textContent = open;
  document.getElementById('stat-done').textContent = done;
  document.getElementById('stat-pct').textContent = pct + '%';
  document.getElementById('progress-fill').style.width = pct + '%';
}


// ---------- boot ----------

document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  });
  document.getElementById('new-list-btn').addEventListener('click', openNewListModal);
  document.getElementById('modal-cancel').addEventListener('click', () => hideModal('task-modal'));
  document.getElementById('list-cancel').addEventListener('click', () => hideModal('list-modal'));
  document.getElementById('task-form').addEventListener('submit', submitTaskForm);
  document.getElementById('list-form').addEventListener('submit', submitListForm);
  document.getElementById('quick-add').addEventListener('submit', handleQuickAddSubmit);

  renderViewTabs();
  await refreshLists();
  await refreshTasks();
});

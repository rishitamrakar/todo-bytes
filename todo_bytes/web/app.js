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
  // Hint text only relevant when reordering is allowed (open view)
  document.getElementById('reorder-hint').hidden = state.activeView !== 'open';
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
  li.className = 'task' + (task.status === 'done' ? ' done' : '');
  li.dataset.taskId = task.id;
  li.innerHTML = `
    <span class="drag-handle">⋮⋮</span>
    <span class="task-name">${escape(task.name)}</span>
    <span class="due ${dueClass(task.due)}">${task.due ? formatDate(task.due) : ''}</span>
    <span class="tags">${(task.tags || []).map(t => `<span class="tag">${escape(t)}</span>`).join('')}</span>
    <span>${task.project ? `<span class="project">${escape(task.project)}</span>` : ''}</span>
    <span class="actions">
      ${task.status === 'open' ? '<button class="icon-btn success" data-action="done" title="Mark done">✓</button>' : ''}
      <button class="icon-btn" data-action="edit" title="Edit">✎</button>
      <button class="icon-btn danger" data-action="delete" title="Delete">✕</button>
    </span>
  `;
  wireTaskRowEvents(li, task);
  return li;
}

function wireTaskRowEvents(li, task) {
  li.querySelector('.task-name').addEventListener('click', () => openEditModal(task));
  li.querySelectorAll('.icon-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      handleTaskAction(btn.dataset.action, task);
    });
  });
}

function handleTaskAction(action, task) {
  if (action === 'done') return markTaskDone(task);
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

async function markTaskDone(task) {
  await api.markDone(state.activeList, task.id);
  await refreshLists();
  await refreshTasks();
}

async function deleteTask(task) {
  if (!confirm(`Delete "${task.name}"?`)) return;
  await api.deleteTask(state.activeList, task.id);
  await refreshLists();
  await refreshTasks();
}


// ---------- modal: add/edit task ----------

function openAddModal() {
  state.editingTaskId = null;
  document.getElementById('modal-title').textContent = 'Add task';
  fillTaskForm({ name: '', due: '', tags: [], project: '' });
  showModal('task-modal');
}

function openEditModal(task) {
  state.editingTaskId = task.id;
  document.getElementById('modal-title').textContent = 'Edit task';
  fillTaskForm(task);
  showModal('task-modal');
}

function fillTaskForm(task) {
  const form = document.getElementById('task-form');
  form.elements.name.value = task.name || '';
  form.elements.due.value = task.due || '';
  form.elements.tags.value = (task.tags || []).join(', ');
  form.elements.project.value = task.project || '';
}

async function submitTaskForm(event) {
  event.preventDefault();
  const form = event.target;
  const payload = readTaskForm(form);
  try {
    if (state.editingTaskId === null) {
      await api.createTask({ list: state.activeList, ...payload });
    } else {
      await api.updateTask(state.activeList, state.editingTaskId, payload);
    }
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
    due: form.elements.due.value || null,
    tags,
    project: form.elements.project.value.trim() || null,
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

function formatDate(iso) {
  return iso;  // already in YYYY-MM-DD which is fine
}

function dueClass(iso) {
  if (!iso) return '';
  const today = new Date().toISOString().slice(0, 10);
  if (iso < today) return 'overdue';
  if (iso === today) return 'today';
  return '';
}


// ---------- boot ----------

document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  });
  document.getElementById('add-task-btn').addEventListener('click', openAddModal);
  document.getElementById('new-list-btn').addEventListener('click', openNewListModal);
  document.getElementById('modal-cancel').addEventListener('click', () => hideModal('task-modal'));
  document.getElementById('list-cancel').addEventListener('click', () => hideModal('list-modal'));
  document.getElementById('task-form').addEventListener('submit', submitTaskForm);
  document.getElementById('list-form').addEventListener('submit', submitListForm);

  renderViewTabs();
  await refreshLists();
  await refreshTasks();
});

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
  editingTaskProject: null,  // project the task being edited belongs to (needed in All Projects view)
  // Sidebar filters — status + tags. Both must pass for a project to show.
  // Default: active statuses; all tags + untagged checked.
  visibleStatuses: new Set(['todo', 'in-progress']),
  visibleTags: new Set(),  // populated from current projects on each refresh
  showUntagged: true,
  // Pending state — only mutated while a filter panel is open.
  // Committed to the visible* state on Apply, discarded on Cancel.
  pending: {
    statuses: null,
    tags: null,
    showUntagged: null,
  },
};

const ALL_PROJECTS = '__all__';
const ALL_STATUS_VALUES = ['todo', 'in-progress', 'done', 'hold', 'cancelled'];


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
  async getProject(name) {
    return fetchJson(`/api/projects/${encodeURIComponent(name)}`);
  },
  async updateProject(name, payload) {
    return fetchJson(`/api/projects/${encodeURIComponent(name)}`, { method: 'PATCH', body: payload });
  },
  async deleteProject(name) {
    return fetchJson(`/api/lists/${encodeURIComponent(name)}`, { method: 'DELETE' });
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

function visibleProjects() {
  return state.lists.filter(p =>
    state.visibleStatuses.has(p.status || 'todo') && projectPassesTagFilter(p)
  );
}

function projectPassesTagFilter(project) {
  const tags = project.tags || [];
  if (tags.length === 0) return state.showUntagged;
  return tags.some(t => state.visibleTags.has(t));
}

function renderLists() {
  const el = document.getElementById('lists');
  el.innerHTML = '';
  const projects = visibleProjects();
  projects.forEach(p => el.appendChild(buildListItem(p)));
  renderAllProjectsButton(projects);
}

function renderAllProjectsButton(visible) {
  const btn = document.getElementById('all-projects-btn');
  btn.classList.toggle('active', state.activeList === ALL_PROJECTS);
  document.getElementById('all-count').textContent = `${visible.length}/${state.lists.length}`;
}

function renderTagFilter() {
  const el = document.getElementById('tag-filter-list');
  el.innerHTML = '';
  const allTags = collectAllTags();
  const hasUntagged = state.lists.some(p => !p.tags || p.tags.length === 0);

  // Render from pending state if the panel is open, else from actual state.
  // (Tag filter is dynamic so we always re-render rather than just sync.)
  const tagSet = state.pending.tags !== null ? state.pending.tags : state.visibleTags;
  const showUntagged = state.pending.showUntagged !== null ? state.pending.showUntagged : state.showUntagged;

  allTags.forEach(tag => el.appendChild(buildTagCheckbox(tag, tagSet.has(tag))));
  if (hasUntagged) el.appendChild(buildUntaggedCheckbox(showUntagged));
  if (allTags.length === 0 && !hasUntagged) {
    el.innerHTML = '<div style="color: var(--text-dim); font-size: 12px;">No tags yet. Add tags via project edit.</div>';
  }
}

function collectAllTags() {
  const set = new Set();
  state.lists.forEach(p => (p.tags || []).forEach(t => set.add(t)));
  return [...set].sort();
}

function buildTagCheckbox(tag, checked) {
  const lbl = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = checked;
  cb.dataset.tag = tag;
  cb.addEventListener('change', () => {
    if (state.pending.tags === null) return;  // panel not open
    if (cb.checked) state.pending.tags.add(tag);
    else state.pending.tags.delete(tag);
  });
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode(' ' + tag));
  return lbl;
}

function buildUntaggedCheckbox(checked) {
  const lbl = document.createElement('label');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = checked;
  cb.addEventListener('change', () => {
    if (state.pending.showUntagged === null) return;  // panel not open
    state.pending.showUntagged = cb.checked;
  });
  lbl.appendChild(cb);
  const span = document.createElement('span');
  span.style.fontStyle = 'italic';
  span.style.color = 'var(--text-dim)';
  span.textContent = ' (no tag)';
  lbl.appendChild(span);
  return lbl;
}

function buildListItem(project) {
  const div = document.createElement('div');
  const status = project.status || 'todo';
  div.className = 'list-item status-' + status + (project.name === state.activeList ? ' active' : '');
  div.innerHTML = `
    <span style="display:flex; align-items:center; flex:1;">
      <span class="project-status-dot"></span>
      ${escape(project.name)}
      ${project.name === state.defaultList ? '<span class="default-mark">★</span>' : ''}
    </span>
    <button class="edit-btn" data-action="edit-project" title="Edit project">✎</button>
    <span class="count">${project.open}/${project.total}</span>
  `;
  div.addEventListener('click', e => {
    if (e.target.closest('[data-action="edit-project"]')) {
      e.stopPropagation();
      openEditProjectModal(project.name);
      return;
    }
    switchList(project.name);
  });
  return div;
}


// ---------- render: views tabs ----------

function renderViewTabs() {
  document.querySelectorAll('.view-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.view === state.activeView);
  });
  // Hint text + quick-add only on Open view of a single project (not All).
  const isOpenView = state.activeView === 'open';
  const isSingleProject = state.activeList !== ALL_PROJECTS;
  document.getElementById('reorder-hint').hidden = !(isOpenView && isSingleProject);
  document.getElementById('quick-add').hidden = !(isOpenView && isSingleProject);
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
  // Drag-reorder only makes sense within a single project on the open view.
  if (state.activeView === 'open' && state.activeList !== ALL_PROJECTS) {
    enableDragReorder(ul);
  }
}

function buildTaskRow(task) {
  const li = document.createElement('li');
  li.className = 'task ' + task.status;  // status used as a CSS modifier
  li.dataset.taskId = task.id;
  // In the All view, show project as a badge so user knows where each task is from.
  // In a single-project view, the project is implicit — hide the badge.
  const showProjectBadge = state.activeList === ALL_PROJECTS;
  const hasContent = (task.description && task.description.trim()) || (task.notes && task.notes.trim());
  li.innerHTML = `
    <span class="drag-handle" title="Drag to reorder">⋮⋮</span>
    <button class="status-circle" data-action="toggle-done" title="${statusTitle(task.status)}"></button>
    <span class="task-name">
      ${escape(task.name)}
      ${hasContent ? '<span class="has-content" title="Has description / notes" data-action="edit">📄</span>' : ''}
    </span>
    <span class="due ${dueClass(task.due)}">${formatDue(task.due)}</span>
    <span class="tags">${(task.tags || []).map(t => `<span class="tag">${escape(t)}</span>`).join('')}</span>
    <span>${showProjectBadge && task.project ? `<span class="project-badge">${escape(task.project)}</span>` : ''}</span>
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
  // Auto-include any tags discovered on existing projects
  collectAllTags().forEach(t => state.visibleTags.add(t));
  if (!state.activeList && state.lists.length > 0) {
    state.activeList = state.defaultList || state.lists[0].name;
  }
  renderLists();
  renderTagFilter();
  updateListTitle();
  renderStats();
}

async function refreshTasks() {
  if (!state.activeList) return;
  if (state.activeList === ALL_PROJECTS) {
    state.tasks = await fetchAllVisibleTasks();
  } else {
    const data = await api.getTasks(state.activeList, state.activeView);
    state.tasks = data.tasks;
  }
  renderTasks();
}

async function fetchAllVisibleTasks() {
  const projects = visibleProjects();
  if (projects.length === 0) return [];
  const results = await Promise.all(
    projects.map(p => api.getTasks(p.name, state.activeView).catch(() => ({ tasks: [] })))
  );
  // Combine, then sort by due date then priority (most useful in cross-project view).
  return results
    .flatMap(r => r.tasks)
    .sort((a, b) => {
      const ad = a.due || '9999-12-31';
      const bd = b.due || '9999-12-31';
      if (ad !== bd) return ad < bd ? -1 : 1;
      return (a.priority || 0) - (b.priority || 0);
    });
}

function switchList(name) {
  state.activeList = name;
  renderLists();
  renderViewTabs();
  updateListTitle();
  renderStats();
  refreshTasks();
}

function switchToAllProjects() {
  state.activeList = ALL_PROJECTS;
  renderLists();
  renderViewTabs();
  updateListTitle();
  renderStats();
  refreshTasks();
}

function switchView(view) {
  state.activeView = view;
  renderViewTabs();
  refreshTasks();
}

function updateListTitle() {
  const title = state.activeList === ALL_PROJECTS
    ? `All Projects (${visibleProjects().length} of ${state.lists.length})`
    : (state.activeList || '—');
  document.getElementById('list-title').textContent = title;
}

// In All Projects view state.activeList is the sentinel '__all__'. Task-level
// operations must target the task's own project, not the sentinel.
function projectForTask(task) {
  return state.activeList === ALL_PROJECTS ? task.project : state.activeList;
}

async function toggleTaskDone(task) {
  // Click the circle: done ↔ todo. Other statuses (hold, cancelled) need the modal.
  const project = projectForTask(task);
  if (task.status === 'done') {
    await api.reopen(project, task.id);
  } else if (task.status === 'todo' || task.status === 'in-progress') {
    await api.markDone(project, task.id);
  } else {
    return;  // hold, cancelled — use edit modal
  }
  await refreshLists();
  await refreshTasks();
}

async function deleteTask(task) {
  if (!confirm(`Delete "${task.name}"?`)) return;
  await api.deleteTask(projectForTask(task), task.id);
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


// ---------- new project (inline in sidebar) ----------

async function handleNewProjectSubmit(event) {
  event.preventDefault();
  const input = document.getElementById('new-project-input');
  const name = input.value.trim();
  if (!name) return;
  try {
    await api.createList(name);
  } catch (err) {
    alert('Create project failed: ' + err.message);
    return;
  }
  input.value = '';
  state.activeList = name;
  await refreshLists();
  await refreshTasks();
  input.focus();
}


// ---------- sidebar filters (status + tags) ----------
//
// Pending-apply model: opening a panel snapshots current state into
// state.pending. Checkboxes / Select all / Deselect all only mutate the
// pending state. The actual filter doesn't change until the user clicks
// Apply. Cancel (or closing the panel) discards.

function openFilterPanel(target) {
  closeAllFilterPanels();
  if (target === 'status') {
    state.pending.statuses = new Set(state.visibleStatuses);
    syncStatusCheckboxesFromPending();
  } else if (target === 'tag') {
    state.pending.tags = new Set(state.visibleTags);
    state.pending.showUntagged = state.showUntagged;
    renderTagFilter();  // renders from pending state
  }
  document.getElementById(`${target}-filter`).hidden = false;
  document.getElementById(`${target}-filter-btn`).classList.add('active');
}

function toggleFilterPanel(target) {
  const panel = document.getElementById(`${target}-filter`);
  if (panel.hidden) openFilterPanel(target);
  else closeAllFilterPanels();  // clicking the active chip closes (= cancel)
}

function closeAllFilterPanels() {
  document.querySelectorAll('.filter-panel').forEach(p => p.hidden = true);
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  // Clear any pending state — closing without Apply discards
  state.pending.statuses = null;
  state.pending.tags = null;
  state.pending.showUntagged = null;
}

function handleStatusCheckboxChange(event) {
  const cb = event.target;
  if (cb.tagName !== 'INPUT') return;
  if (state.pending.statuses === null) return;  // panel not open
  const status = cb.dataset.status;
  if (cb.checked) state.pending.statuses.add(status);
  else state.pending.statuses.delete(status);
}

function syncStatusCheckboxesFromPending() {
  document.querySelectorAll('#status-filter input[type=checkbox]').forEach(cb => {
    cb.checked = state.pending.statuses.has(cb.dataset.status);
  });
}

function handleFilterAction(event) {
  const btn = event.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const target = btn.dataset.target;
  if (action === 'apply') applyFilter(target);
  else if (action === 'select-all') selectAllInPending(target);
}

// Double-click on Select all = deselect all. Single-click selects, dblclick
// fires after a brief select-all flicker which doubles as visual feedback.
function handleFilterDblClick(event) {
  const btn = event.target.closest('button[data-action="select-all"]');
  if (!btn) return;
  deselectAllInPending(btn.dataset.target);
}

function selectAllInPending(target) {
  if (target === 'status') {
    state.pending.statuses = new Set(ALL_STATUS_VALUES);
    syncStatusCheckboxesFromPending();
  } else if (target === 'tag') {
    state.pending.tags = new Set(collectAllTags());
    state.pending.showUntagged = true;
    renderTagFilter();
  }
}

function deselectAllInPending(target) {
  if (target === 'status') {
    state.pending.statuses = new Set();
    syncStatusCheckboxesFromPending();
  } else if (target === 'tag') {
    state.pending.tags = new Set();
    state.pending.showUntagged = false;
    renderTagFilter();
  }
}

function applyFilter(target) {
  if (target === 'status' && state.pending.statuses !== null) {
    state.visibleStatuses = state.pending.statuses;
  } else if (target === 'tag' && state.pending.tags !== null) {
    state.visibleTags = state.pending.tags;
    state.showUntagged = state.pending.showUntagged;
  }
  closeAllFilterPanels();
  renderLists();
  // If the active project is now filtered out, fall back to All Projects view
  if (state.activeList && state.activeList !== ALL_PROJECTS) {
    const stillVisible = visibleProjects().some(p => p.name === state.activeList);
    if (!stillVisible) switchToAllProjects();
  }
}


// ---------- modal: edit project ----------

async function openEditProjectModal(projectName) {
  let project;
  try {
    project = await api.getProject(projectName);
  } catch (err) {
    alert('Could not load project: ' + err.message);
    return;
  }
  const form = document.getElementById('project-form');
  form.elements.name.value = project.name;
  form.elements.description.value = project.description || '';
  form.elements.status.value = project.status || 'todo';
  const { date: pDate, time: pTime } = splitDueIso(project.due);
  form.elements.due_date.value = pDate;
  form.elements.due_time.value = pTime;
  form.elements.tags.value = (project.tags || []).join(', ');
  form.dataset.editing = projectName;
  showModal('project-modal');
}

async function submitProjectForm(event) {
  event.preventDefault();
  const form = event.target;
  const name = form.dataset.editing;
  const tags = (form.elements.tags.value || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  const payload = {
    description: form.elements.description.value.trim() || null,
    status: form.elements.status.value,
    due: combineDateTimeToIso(form.elements.due_date.value, form.elements.due_time.value),
    tags,
  };
  try {
    await api.updateProject(name, payload);
  } catch (err) {
    alert('Save failed: ' + err.message);
    return;
  }
  hideModal('project-modal');
  await refreshLists();
}

async function deleteActiveProject() {
  const form = document.getElementById('project-form');
  const name = form.dataset.editing;
  if (!confirm(`Delete project "${name}" and all its tasks?`)) return;
  try {
    await api.deleteProject(name);
  } catch (err) {
    alert('Delete failed: ' + err.message);
    return;
  }
  hideModal('project-modal');
  if (state.activeList === name) state.activeList = null;
  await refreshLists();
  await refreshTasks();
}


// ---------- modal: edit task ----------

function openEditModal(task) {
  state.editingTaskId = task.id;
  state.editingTaskProject = projectForTask(task);
  document.getElementById('modal-title').textContent = 'Edit task';
  fillTaskForm(task);
  showModal('task-modal');
}

function fillTaskForm(task) {
  const form = document.getElementById('task-form');
  form.elements.name.value = task.name || '';
  const { date: dueDate, time: dueTime } = splitDueIso(task.due);
  form.elements.due_date.value = dueDate;
  form.elements.due_time.value = dueTime;
  form.elements.tags.value = (task.tags || []).join(', ');
  form.elements.status.value = task.status || 'todo';
  form.elements.description.value = task.description || '';
  form.elements.notes.value = task.notes || '';
  document.getElementById('meta-project').textContent = task.project || '—';
  document.getElementById('meta-created').textContent = task.created || '—';
}

async function submitTaskForm(event) {
  event.preventDefault();
  if (state.editingTaskId === null) return;  // edit-only modal
  const payload = readTaskForm(event.target);
  try {
    await api.updateTask(state.editingTaskProject, state.editingTaskId, payload);
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
    due: combineDateTimeToIso(form.elements.due_date.value, form.elements.due_time.value),
    tags,
    status: form.elements.status.value,
    description: form.elements.description.value.trim() || null,
    notes: form.elements.notes.value || null,  // preserve newlines
    // project intentionally omitted — it's auto-set to the parent project
  };
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

// We split datetime into separate date + time inputs (native datetime-local
// has no explicit Apply button, which is confusing). Time is optional — if
// the user leaves it empty we default to end-of-day (23:59).
function splitDueIso(iso) {
  if (!iso) return { date: '', time: '' };
  const datePart = iso.slice(0, 10);
  const timePart = iso.slice(11, 16);  // HH:MM
  // Hide the default end-of-day time — it's just our convention, not
  // something the user picked.
  if (timePart === '23:59') return { date: datePart, time: '' };
  return { date: datePart, time: timePart };
}

function combineDateTimeToIso(dateStr, timeStr) {
  if (!dateStr) return null;
  const time = timeStr || '23:59:59';  // end-of-day default when no time given
  // Ensure seconds are present
  const fullTime = time.length === 5 ? time + ':00' : time;
  return `${dateStr}T${fullTime}`;
}

// Update the stats card in the side pane.
// In single-project view: stats for that project.
// In All view: combined stats across all visible projects.
function renderStats() {
  let open = 0, done = 0;
  if (state.activeList === ALL_PROJECTS) {
    visibleProjects().forEach(p => { open += p.open || 0; done += p.done || 0; });
  } else {
    const summary = state.lists.find(l => l.name === state.activeList);
    open = summary ? summary.open : 0;
    done = summary ? summary.done : 0;
  }
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

  // Task modal
  document.getElementById('modal-cancel').addEventListener('click', () => hideModal('task-modal'));
  document.getElementById('task-form').addEventListener('submit', submitTaskForm);

  // Inline task quick-add
  document.getElementById('quick-add').addEventListener('submit', handleQuickAddSubmit);

  // Inline new-project form (sidebar)
  document.getElementById('new-project-form').addEventListener('submit', handleNewProjectSubmit);

  // Sidebar filters — chips toggle panels; panel buttons handle actions
  document.getElementById('status-filter-btn').addEventListener('click', () => toggleFilterPanel('status'));
  document.getElementById('tag-filter-btn').addEventListener('click', () => toggleFilterPanel('tag'));
  document.getElementById('status-filter').addEventListener('change', handleStatusCheckboxChange);
  document.getElementById('status-filter').addEventListener('click', handleFilterAction);
  document.getElementById('status-filter').addEventListener('dblclick', handleFilterDblClick);
  document.getElementById('tag-filter').addEventListener('click', handleFilterAction);
  document.getElementById('tag-filter').addEventListener('dblclick', handleFilterDblClick);

  // 'All Projects' button at the top of the sidebar
  document.getElementById('all-projects-btn').addEventListener('click', switchToAllProjects);

  // Project edit modal
  document.getElementById('project-cancel').addEventListener('click', () => hideModal('project-modal'));
  document.getElementById('project-form').addEventListener('submit', submitProjectForm);
  document.getElementById('project-delete').addEventListener('click', deleteActiveProject);

  renderViewTabs();
  await refreshLists();
  await refreshTasks();
});

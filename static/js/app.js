// Глобальные переменные
let currentFetchTaskId = null;

// Элементы DOM
const urlInput = document.getElementById('url-input');
const downloadFolderInput = document.getElementById('download-folder');
const audioOnlyCheckbox = document.getElementById('audio-only');
const fetchFormatsBtn = document.getElementById('fetch-formats-btn');
const formatsSection = document.getElementById('formats-section');
const formatsSelect = document.getElementById('formats-select');
const addToQueueBtn = document.getElementById('add-to-queue-btn');
const queueSection = document.getElementById('queue-section');
const queueList = document.getElementById('queue-list');
const queueStartBtn = document.getElementById('queue-start-btn');
const queuePauseBtn = document.getElementById('queue-pause-btn');
const queueStopBtn = document.getElementById('queue-stop-btn');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const statusMessage = document.getElementById('status-message');
const historyList = document.getElementById('history-list');
const deleteModal = document.getElementById('delete-modal');
const deleteHistoryOnlyBtn = document.getElementById('delete-history-only-btn');
const deleteWithFileBtn = document.getElementById('delete-with-file-btn');
const cancelDeleteBtn = document.getElementById('cancel-delete-btn');

// Отправка ошибки на бэкенд
async function logErrorToBackend(type, message, stack, timestamp) {
    try {
        await fetch('/api/log-error', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                type: type,
                message: message,
                stack: stack,
                timestamp: timestamp
            })
        });
    } catch (error) {
        // Если не удалось отправить, хотя бы выводим в консоль
        console.error('Failed to log error to backend:', error);
    }
}

// Инициализация
document.addEventListener('DOMContentLoaded', async () => {
    setupErrorHandling();
    await loadUIState();
    await loadConfig();
    loadHistory();
    loadQueue();
    setupEventListeners();
});

// Настройка глобальной обработки ошибок
function setupErrorHandling() {
    // Обработка необработанных ошибок
    window.addEventListener('error', (event) => {
        logErrorToBackend('error', event.message, event.error?.stack || '', new Date().toISOString());
    });
    
    // Обработка необработанных промисов
    window.addEventListener('unhandledrejection', (event) => {
        logErrorToBackend('unhandledrejection', event.reason?.message || String(event.reason), event.reason?.stack || '', new Date().toISOString());
    });
    
    // Перехват console.error
    const originalConsoleError = console.error;
    console.error = function(...args) {
        originalConsoleError.apply(console, args);
        const message = args.map(arg => {
            if (typeof arg === 'object') {
                try {
                    return JSON.stringify(arg);
                } catch (e) {
                    return String(arg);
                }
            }
            return String(arg);
        }).join(' ');
        logErrorToBackend('console.error', message, '', new Date().toISOString());
    };
}

// Загрузка конфигурации
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        if (!downloadFolderInput.value || downloadFolderInput.value === 'Not specified') {
            downloadFolderInput.value = data.download_folder || 'Not specified';
        }
    } catch (error) {
        console.error('Error loading config:', error);
        logErrorToBackend('loadConfig', error.message, error.stack, new Date().toISOString());
    }
}

// Настройка обработчиков событий
function setupEventListeners() {
    fetchFormatsBtn.addEventListener('click', handleFetchFormats);
    addToQueueBtn.addEventListener('click', handleAddToQueue);
    queueStartBtn.addEventListener('click', handleQueueStart);
    queuePauseBtn.addEventListener('click', handleQueuePause);
    queueStopBtn.addEventListener('click', handleQueueStop);
    deleteHistoryOnlyBtn.addEventListener('click', () => {
        if (currentDeleteHistoryId) {
            deleteHistoryItem(currentDeleteHistoryId, false);
        }
    });
    deleteWithFileBtn.addEventListener('click', () => {
        if (currentDeleteHistoryId) {
            deleteHistoryItem(currentDeleteHistoryId, true);
        }
    });
    cancelDeleteBtn.addEventListener('click', () => {
        hideDeleteModal();
    });
    audioOnlyCheckbox.addEventListener('change', () => {
        handleAudioOnlyChange();
        saveUIState();
    });
    formatsSelect.addEventListener('change', () => {
        saveUIState();
    });
    urlInput.addEventListener('blur', saveUIState);
    downloadFolderInput.addEventListener('blur', saveUIState);
}

// Обработка изменения чекбокса "Только аудио"
function handleAudioOnlyChange() {
    if (audioOnlyCheckbox.checked) {
        formatsSection.style.display = 'none';
    } else {
        formatsSection.style.display = 'block';
    }
}

// Получение форматов
async function handleFetchFormats() {
    const url = urlInput.value.trim();
    if (!url) {
        showStatus('Enter video URL!', 'error');
        return;
    }

    if (audioOnlyCheckbox.checked) {
        showStatus('Audio only mode selected. Formats not needed.', 'info');
        return;
    }

    fetchFormatsBtn.disabled = true;
    showStatus('Fetching formats...', 'info');

    try {
        const response = await fetch('/api/fetch-formats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Error fetching formats');
        }

        const data = await response.json();
        currentFetchTaskId = data.task_id;

        // Проверяем результат каждые 500мс
        checkFormatsResult();
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
        fetchFormatsBtn.disabled = false;
        logErrorToBackend('fetchFormats', error.message, error.stack, new Date().toISOString());
    }
}

// Проверка результата получения форматов
async function checkFormatsResult() {
    if (!currentFetchTaskId) return;

    try {
        const response = await fetch(`/api/get-formats/${currentFetchTaskId}`);
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        if (data.formats) {
            // Форматы получены
            formatsSelect.innerHTML = '';
            data.formats.forEach((fmt, index) => {
                const option = document.createElement('option');
                const hasFfmpeg = fmt.format && typeof fmt.format === 'string' && fmt.format.includes('+');
                const label = `${fmt.resolution || 'audio'} | ${fmt.ext} | ${fmt.format_note || ''}${hasFfmpeg ? ' +ffmpeg' : ''}`;
                option.textContent = label;
                option.value = fmt.format_id;
                formatsSelect.appendChild(option);
            });
            formatsSection.style.display = 'block';
            showStatus(`Formats fetched for: ${data.title || 'video'}`, 'success');
            fetchFormatsBtn.disabled = false;
            currentFetchTaskId = null;
        } else if (data.status === 'fetching') {
            // Еще загружается
            setTimeout(checkFormatsResult, 500);
        }
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
        fetchFormatsBtn.disabled = false;
        currentFetchTaskId = null;
        logErrorToBackend('checkFormatsResult', error.message, error.stack, new Date().toISOString());
    }
}


// Показать статус
function showStatus(message, type) {
    statusMessage.textContent = message;
    statusMessage.className = 'status-message ' + type;
    statusMessage.style.display = 'block';

    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            statusMessage.style.display = 'none';
        }, 5000);
    }
}

// Обновление прогресса
function updateProgress(percent) {
    progressBar.style.width = percent + '%';
    progressText.textContent = Math.round(percent) + '%';
}

// Сохранение UI состояния
async function saveUIState() {
    const state = {
        url: urlInput.value,
        format_id: formatsSelect.value,
        audio_only: audioOnlyCheckbox.checked,
        download_folder: downloadFolderInput.value,
        formats_visible: formatsSection.style.display !== 'none'
    };
    await fetch('/api/ui-state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state)
    });
}

// Загрузка UI состояния
async function loadUIState() {
    const response = await fetch('/api/ui-state');
    const state = await response.json();
    
    if (state.url) urlInput.value = state.url;
    if (state.format_id) formatsSelect.value = state.format_id;
    if (state.audio_only === 'true') audioOnlyCheckbox.checked = true;
    if (state.download_folder) downloadFolderInput.value = state.download_folder;
    if (state.formats_visible === 'true') formatsSection.style.display = 'block';
    if (state.audio_only === 'true') handleAudioOnlyChange();
}

// Добавление в очередь
async function handleAddToQueue() {
    const url = urlInput.value.trim();
    if (!url) {
        showStatus('Enter video URL!', 'error');
            return;
        }

    const audioOnly = audioOnlyCheckbox.checked;
    const formatId = audioOnly ? null : formatsSelect.value;
    
    if (!audioOnly && !formatId) {
        showStatus('Select a format!', 'error');
        return;
    }

    await fetch('/api/queue/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            url,
            title: '',
            format_id: formatId,
            audio_only: audioOnly,
            download_folder: downloadFolderInput.value
        })
    });

    showStatus('Added to queue', 'success');
    loadQueue();
    queueSection.style.display = 'block';
}

// Загрузка очереди
async function loadQueue() {
    const response = await fetch('/api/queue/list');
    const data = await response.json();

    queueList.innerHTML = '';

    let activeProgresses = [];
    if (data.queue.length > 0) {
        data.queue.forEach(item => {
            const div = document.createElement('div');
            div.className = 'queue-item';
            
            const info = document.createElement('div');
            info.className = 'queue-item-info';
            
            const title = document.createElement('div');
            title.className = 'queue-item-title';
            title.textContent = item.title || item.url;
            
            const status = document.createElement('div');
            status.className = 'queue-item-status';
            const statusText = {
                'pending': 'Pending',
                'downloading': 'Downloading',
                'paused': 'Paused',
                'finished': 'Completed',
                'error': 'Error',
                'cancelled': 'Cancelled'
            }[item.status] || item.status;
            status.textContent = `Status: ${statusText}`;
            if (item.progress !== undefined && item.status === 'downloading') {
                status.textContent += ` (${Math.round(item.progress)}%)`;
                activeProgresses.push(item.progress);
            }
            
            info.appendChild(title);
            info.appendChild(status);
            div.appendChild(info);
            
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'delete-btn';
            deleteBtn.textContent = '×';
            deleteBtn.title = 'Delete';
            deleteBtn.onclick = () => deleteQueueItem(item.id);
            div.appendChild(deleteBtn);
            
            queueList.appendChild(div);
        });
        queueSection.style.display = 'block';
    } else {
        queueSection.style.display = 'none';
    }
    
    if (activeProgresses.length > 0) {
        const avgProgress = activeProgresses.reduce((a, b) => a + b, 0) / activeProgresses.length;
        updateProgress(avgProgress);
    } else {
        updateProgress(0);
    }
    
    const hasActiveDownloads = data.queue.some(item => item.status === 'downloading');
    if (!hasActiveDownloads) {
        stopProgressUpdate();
    }
    
    if (data.queue.length < previousQueueLength) {
        loadHistory();
    }
    previousQueueLength = data.queue.length;
}

// Запуск очереди
async function handleQueueStart() {
    await fetch('/api/queue/start', { method: 'POST' });
    showStatus('Download started', 'success');
    loadQueue();
    startProgressUpdate();
}

// Пауза очереди
async function handleQueuePause() {
    const isPaused = queuePauseBtn.textContent === 'Resume';
    const endpoint = isPaused ? 'resume' : 'pause';
    await fetch(`/api/queue/${endpoint}`, { method: 'POST' });
    queuePauseBtn.textContent = isPaused ? 'Pause' : 'Resume';
    showStatus(isPaused ? 'Download resumed' : 'Download paused', 'info');
    loadQueue();
}

// Остановка очереди
async function handleQueueStop() {
    await fetch('/api/queue/stop', { method: 'POST' });
    showStatus('Download stopped', 'info');
    stopProgressUpdate();
    loadQueue();
}

// Обновление прогресса
let progressUpdateInterval = null;
let previousQueueLength = 0;

function startProgressUpdate() {
    if (progressUpdateInterval) return;
    previousQueueLength = 0;
    progressUpdateInterval = setInterval(() => {
        loadQueue();
    }, 1000);
}

function stopProgressUpdate() {
    if (progressUpdateInterval) {
        clearInterval(progressUpdateInterval);
        progressUpdateInterval = null;
    }
}


// Загрузка истории
async function loadHistory() {
    const response = await fetch('/api/history');
    const data = await response.json();

    historyList.innerHTML = '';

    if (data.history.length > 0) {
        data.history.forEach(item => {
            const div = document.createElement('div');
            div.className = 'history-item';

            const info = document.createElement('div');
            info.className = 'history-item-info';

            const title = document.createElement('div');
            title.className = 'history-item-title';
            title.textContent = item.title || item.url;

            const details = document.createElement('div');
            details.className = 'history-item-details';
            const statusText = item.status === 'finished' ? 'Completed' : 
                             item.status === 'error' ? 'Error' : 'Cancelled';
            details.textContent = `${statusText} | ${new Date(item.created_at).toLocaleString()}`;

            info.appendChild(title);
            info.appendChild(details);
            div.appendChild(info);
            
            const buttonsDiv = document.createElement('div');
            buttonsDiv.className = 'history-item-buttons';
            
            const copyUrlBtn = document.createElement('button');
            copyUrlBtn.className = 'action-btn';
            copyUrlBtn.textContent = '🔗';
            copyUrlBtn.title = 'Copy URL';
            copyUrlBtn.onclick = () => copyHistoryUrl(item.url);
            buttonsDiv.appendChild(copyUrlBtn);
            
            if (item.status === 'finished' && item.file_path) {
                const openFileBtn = document.createElement('button');
                openFileBtn.className = 'action-btn';
                openFileBtn.textContent = '📄';
                openFileBtn.title = 'Open file';
                openFileBtn.onclick = () => openHistoryFile(item.id);
                buttonsDiv.appendChild(openFileBtn);
                
                const openFolderBtn = document.createElement('button');
                openFolderBtn.className = 'action-btn';
                openFolderBtn.textContent = '📁';
                openFolderBtn.title = 'Open folder';
                openFolderBtn.onclick = () => openHistoryFolder(item.id);
                buttonsDiv.appendChild(openFolderBtn);
            }
            
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'delete-btn';
            deleteBtn.textContent = '×';
            deleteBtn.title = 'Delete';
            deleteBtn.onclick = () => showDeleteModal(item.id);
            buttonsDiv.appendChild(deleteBtn);
            
            div.appendChild(buttonsDiv);
            historyList.appendChild(div);
        });
    } else {
        historyList.innerHTML = '<p style="color: #718096; text-align: center;">History is empty</p>';
    }
}

// Удаление элемента из очереди
async function deleteQueueItem(queueId) {
    await fetch(`/api/queue/delete/${queueId}`, { method: 'POST' });
    loadQueue();
}

// Открытие файла из истории
async function openHistoryFile(historyId) {
    const response = await fetch(`/api/history/file/${historyId}`);
    const data = await response.json();
    if (data.file_path) {
        await fetch('/api/open-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: data.file_path })
        });
    }
}

// Открытие папки из истории
async function openHistoryFolder(historyId) {
    const response = await fetch(`/api/history/file/${historyId}`);
    const data = await response.json();
    if (data.file_path) {
        await fetch('/api/open-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: data.file_path })
        });
    }
}

// Копирование URL из истории
function copyHistoryUrl(url) {
    navigator.clipboard.writeText(url).then(() => {
        showStatus('URL copied to clipboard', 'success');
    }).catch(() => {
        const textArea = document.createElement('textarea');
        textArea.value = url;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        showStatus('URL copied to clipboard', 'success');
    });
}

// Удаление элемента из истории
let currentDeleteHistoryId = null;

function showDeleteModal(historyId) {
    currentDeleteHistoryId = historyId;
    deleteModal.style.display = 'flex';
}

deleteModal.addEventListener('click', (e) => {
    if (e.target === deleteModal) {
        hideDeleteModal();
    }
});

function hideDeleteModal() {
    deleteModal.style.display = 'none';
    currentDeleteHistoryId = null;
}

async function deleteHistoryItem(historyId, deleteFile) {
    await fetch(`/api/history/delete/${historyId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delete_file: deleteFile })
    });
    hideDeleteModal();
    loadHistory();
}



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
document.addEventListener('DOMContentLoaded', () => {
    setupErrorHandling();
    loadConfig();
    loadUIState();
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
        downloadFolderInput.value = data.download_folder || 'Не указана';
    } catch (error) {
        console.error('Ошибка загрузки конфигурации:', error);
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
        showStatus('Введите URL видео!', 'error');
        return;
    }

    if (audioOnlyCheckbox.checked) {
        showStatus('Режим "Только аудио" выбран. Форматы не нужны.', 'info');
        return;
    }

    fetchFormatsBtn.disabled = true;
    showStatus('Получение форматов...', 'info');

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
            throw new Error(error.error || 'Ошибка получения форматов');
        }

        const data = await response.json();
        currentFetchTaskId = data.task_id;

        // Проверяем результат каждые 500мс
        checkFormatsResult();
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
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
            showStatus(`Форматы получены для: ${data.title || 'видео'}`, 'success');
            fetchFormatsBtn.disabled = false;
            currentFetchTaskId = null;
        } else if (data.status === 'fetching') {
            // Еще загружается
            setTimeout(checkFormatsResult, 500);
        }
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
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

// Сохранение UI состояния
async function saveUIState() {
    try {
        const state = {
            url: urlInput.value,
            format_id: formatsSelect.value,
            audio_only: audioOnlyCheckbox.checked,
            download_folder: downloadFolderInput.value,
            formats_visible: formatsSection.style.display !== 'none'
        };
        await fetch('/api/ui-state', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(state)
        });
    } catch (error) {
        console.error('Ошибка сохранения UI состояния:', error);
    }
}

// Загрузка UI состояния
async function loadUIState() {
    try {
        const response = await fetch('/api/ui-state');
        const state = await response.json();
        
        if (state.url) urlInput.value = state.url;
        if (state.format_id) formatsSelect.value = state.format_id;
        if (state.audio_only !== undefined) audioOnlyCheckbox.checked = state.audio_only === 'true';
        if (state.download_folder) downloadFolderInput.value = state.download_folder;
        if (state.formats_visible === 'true') {
            formatsSection.style.display = 'block';
        }
        if (state.audio_only === 'true') {
            handleAudioOnlyChange();
        }
    } catch (error) {
        console.error('Ошибка загрузки UI состояния:', error);
    }
}

// Добавление в очередь
async function handleAddToQueue() {
    const url = urlInput.value.trim();
    if (!url) {
        showStatus('Введите URL видео!', 'error');
        return;
    }

    const audioOnly = audioOnlyCheckbox.checked;
    let formatId = null;
    let title = '';

    if (!audioOnly) {
        formatId = formatsSelect.value;
        if (!formatId) {
            showStatus('Выберите формат!', 'error');
            return;
        }
    }

    try {
        const response = await fetch('/api/queue/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url,
                title,
                format_id: formatId,
                audio_only: audioOnly,
                download_folder: downloadFolderInput.value
            })
        });

        if (!response.ok) {
            throw new Error('Ошибка добавления в очередь');
        }

        showStatus('Добавлено в очередь', 'success');
        loadQueue();
        queueSection.style.display = 'block';
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
    }
}

// Загрузка очереди
async function loadQueue() {
    try {
        const response = await fetch('/api/queue/list');
        const data = await response.json();

        queueList.innerHTML = '';

        if (data.queue && data.queue.length > 0) {
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
                status.textContent = `Статус: ${item.status}`;
                if (item.progress !== undefined) {
                    status.textContent += ` (${Math.round(item.progress)}%)`;
                }
                
                info.appendChild(title);
                info.appendChild(status);
                div.appendChild(info);
                queueList.appendChild(div);
            });
            queueSection.style.display = 'block';
        } else {
            queueSection.style.display = 'none';
        }
    } catch (error) {
        console.error('Ошибка загрузки очереди:', error);
    }
}

// Запуск очереди
async function handleQueueStart() {
    try {
        await fetch('/api/queue/start', { method: 'POST' });
        showStatus('Загрузка запущена', 'success');
        loadQueue();
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
    }
}

// Пауза очереди
async function handleQueuePause() {
    try {
        const isPaused = queuePauseBtn.textContent === 'Продолжить';
        const endpoint = isPaused ? 'resume' : 'pause';
        await fetch(`/api/queue/${endpoint}`, { method: 'POST' });
        queuePauseBtn.textContent = isPaused ? 'Пауза' : 'Продолжить';
        showStatus(isPaused ? 'Загрузка возобновлена' : 'Загрузка приостановлена', 'info');
        loadQueue();
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
    }
}

// Остановка очереди
async function handleQueueStop() {
    try {
        await fetch('/api/queue/stop', { method: 'POST' });
        showStatus('Загрузка остановлена', 'info');
        loadQueue();
    } catch (error) {
        showStatus('Ошибка: ' + error.message, 'error');
    }
}


// Загрузка истории
async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();

        historyList.innerHTML = '';

        if (data.history && data.history.length > 0) {
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
                const statusText = item.status === 'finished' ? 'Завершено' : 
                                 item.status === 'error' ? 'Ошибка' : 'Отменено';
                details.textContent = `${statusText} | ${new Date(item.created_at).toLocaleString()}`;

                info.appendChild(title);
                info.appendChild(details);
                div.appendChild(info);
                historyList.appendChild(div);
            });
        } else {
            historyList.innerHTML = '<p style="color: #718096; text-align: center;">История пуста</p>';
        }
    } catch (error) {
        console.error('Ошибка загрузки истории:', error);
    }
}

// Форматирование размера файла
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}


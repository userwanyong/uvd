/**
 * SaveIt - 万能视频下载器 前端逻辑
 */

const API_BASE = '/api';

// DOM 元素
const urlInput = document.getElementById('urlInput');
const parseBtn = document.getElementById('parseBtn');
const videoCard = document.getElementById('videoCard');
const videoThumbnail = document.getElementById('videoThumbnail');
const videoDuration = document.getElementById('videoDuration');
const videoTitle = document.getElementById('videoTitle');
const videoUploader = document.getElementById('videoUploader');
const videoDate = document.getElementById('videoDate');
const videoDesc = document.getElementById('videoDesc');
const formatList = document.getElementById('formatList');
const downloadBtn = document.getElementById('downloadBtn');
const progressCard = document.getElementById('progressCard');
const progressLabel = document.getElementById('progressLabel');
const progressPercent = document.getElementById('progressPercent');
const progressFill = document.getElementById('progressFill');
const progressSpeed = document.getElementById('progressSpeed');
const progressSize = document.getElementById('progressSize');
const completeCard = document.getElementById('completeCard');
const downloadFileBtn = document.getElementById('downloadFileBtn');
const newDownloadBtn = document.getElementById('newDownloadBtn');
const errorToast = document.getElementById('errorToast');
const errorMsg = document.getElementById('errorMsg');

let currentVideoInfo = null;
let selectedFormatId = null;
let currentTaskId = null;
let progressTimer = null;

// ===== 工具函数 =====

function humanSize(bytes) {
    if (!bytes) return '--';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return bytes.toFixed(1) + ' ' + units[i];
}

function showError(msg) {
    errorMsg.textContent = msg;
    errorToast.style.display = 'flex';
    setTimeout(() => { errorToast.style.display = 'none'; }, 5000);
}

function hideError() {
    errorToast.style.display = 'none';
}

function setBtnLoading(btn, loading) {
    if (loading) {
        btn.disabled = true;
        btn._prevHTML = btn.innerHTML;
        btn.innerHTML = '<span class="loading"></span> 处理中...';
    } else {
        btn.disabled = false;
        btn.innerHTML = btn._prevHTML || btn.innerHTML;
    }
}

function parseUploadDate(dateStr) {
    if (!dateStr || dateStr.length < 8) return '';
    const y = dateStr.slice(0, 4);
    const m = dateStr.slice(4, 6);
    const d = dateStr.slice(6, 8);
    return `${y}-${m}-${d}`;
}

// ===== 解析视频 =====

async function parseVideo() {
    const url = urlInput.value.trim();
    if (!url) {
        showError('请输入视频链接');
        urlInput.focus();
        return;
    }

    // 简单URL格式校验
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        showError('请输入有效的视频链接（以 http:// 或 https:// 开头）');
        return;
    }

    hideError();
    setBtnLoading(parseBtn, true);

    // 重置UI
    videoCard.style.display = 'none';
    progressCard.style.display = 'none';
    completeCard.style.display = 'none';
    selectedFormatId = null;

    try {
        const resp = await fetch(`${API_BASE}/info`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '解析失败');
        }

        currentVideoInfo = await resp.json();
        showVideoInfo(currentVideoInfo);
    } catch (e) {
        showError(e.message);
    } finally {
        setBtnLoading(parseBtn, false);
    }
}

function showVideoInfo(info) {
    // 缩略图
    videoThumbnail.src = info.thumbnail || '';
    videoThumbnail.onerror = () => { videoThumbnail.src = ''; };

    // 时长
    videoDuration.textContent = info.duration_string || '';

    // 标题
    videoTitle.textContent = info.title || '未知标题';

    // 上传者 & 日期
    videoUploader.textContent = info.uploader || '';
    videoDate.textContent = parseUploadDate(info.upload_date);

    // 描述
    videoDesc.textContent = info.description || '';

    // 格式列表
    buildFormatList(info.formats, info.best_format_id);

    // 显示卡片
    videoCard.style.display = 'block';
    videoCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function buildFormatList(formats, bestFormatId) {
    formatList.innerHTML = '';

    if (!formats || formats.length === 0) {
        formatList.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; padding: 12px;">未获取到可选格式，将使用默认最佳画质下载</div>';
        selectedFormatId = bestFormatId || null;
        return;
    }

    // 去重：相同 resolution 只保留一个（优先选文件大小大的）
    const seen = new Map();
    for (const fmt of formats) {
        const key = fmt.label;
        const existing = seen.get(key);
        if (!existing) {
            seen.set(key, fmt);
        }
    }
    const uniqueFormats = [...seen.values()];

    // 限制显示数量，避免列表太长
    const displayFormats = uniqueFormats.slice(0, 30);

    displayFormats.forEach(fmt => {
        const item = document.createElement('div');
        item.className = 'format-item' + (fmt.format_id === bestFormatId ? ' selected' : '');
        item.dataset.formatId = fmt.format_id;

        const isBest = fmt.format_id === bestFormatId;

        item.innerHTML = `
            <div class="format-item-left">
                <span class="format-badge ${isBest ? 'best' : ''}">${isBest ? '推荐' : '选择'}</span>
                <span class="format-label">${fmt.label}</span>
            </div>
            <span class="format-ext">${fmt.ext ? fmt.ext.toUpperCase() : ''}</span>
        `;

        item.addEventListener('click', () => {
            document.querySelectorAll('.format-item').forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            selectedFormatId = fmt.format_id;
        });

        formatList.appendChild(item);
    });

    if (uniqueFormats.length > 30) {
        const hint = document.createElement('div');
        hint.style.cssText = 'color: var(--text-muted); font-size: 12px; padding: 8px; text-align: center;';
        hint.textContent = `还有 ${uniqueFormats.length - 30} 个格式未显示`;
        formatList.appendChild(hint);
    }

    // 默认选中最佳格式
    selectedFormatId = bestFormatId || displayFormats[0]?.format_id || null;
}

// ===== 下载视频 =====

async function startDownload() {
    const url = urlInput.value.trim();
    if (!url) return;

    hideError();
    setBtnLoading(downloadBtn, true);
    videoCard.style.display = 'none';
    progressCard.style.display = 'block';
    completeCard.style.display = 'none';

    progressLabel.textContent = '正在下载...';
    progressPercent.textContent = '0%';
    progressFill.style.width = '0%';
    progressSpeed.textContent = '速度: --';
    progressSize.textContent = '大小: --';

    try {
        const resp = await fetch(`${API_BASE}/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url,
                format_id: selectedFormatId,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '下载启动失败');
        }

        const data = await resp.json();
        currentTaskId = data.task_id;

        // 开始轮询进度
        pollProgress(currentTaskId);
    } catch (e) {
        showError(e.message);
        progressCard.style.display = 'none';
        videoCard.style.display = 'block';
    } finally {
        setBtnLoading(downloadBtn, false);
    }
}

function pollProgress(taskId) {
    if (progressTimer) clearInterval(progressTimer);

    progressTimer = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/progress/${taskId}`);
            if (!resp.ok) {
                clearInterval(progressTimer);
                return;
            }

            const data = await resp.json();

            // 更新进度UI
            progressPercent.textContent = data.progress.toFixed(1) + '%';
            progressFill.style.width = data.progress + '%';
            progressSpeed.textContent = data.speed > 0
                ? `速度: ${humanSize(data.speed)}/s`
                : '速度: --';
            progressSize.textContent = data.total_bytes > 0
                ? `大小: ${humanSize(data.total_bytes)}`
                : `已下载: ${humanSize(data.downloaded_bytes)}`;

            if (data.status === 'completed') {
                clearInterval(progressTimer);
                progressLabel.textContent = '下载完成!';

                // 显示完成卡片
                setTimeout(() => {
                    progressCard.style.display = 'none';
                    completeCard.style.display = 'block';
                    downloadFileBtn.href = `${API_BASE}/file/${taskId}`;
                    completeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }, 500);
            } else if (data.status === 'error') {
                clearInterval(progressTimer);
                showError('下载失败: ' + data.error);
                progressCard.style.display = 'none';
                videoCard.style.display = 'block';
            }
        } catch (e) {
            clearInterval(progressTimer);
        }
    }, 800);
}

// ===== 事件绑定 =====

parseBtn.addEventListener('click', parseVideo);

urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') parseVideo();
});

downloadBtn.addEventListener('click', startDownload);

newDownloadBtn.addEventListener('click', () => {
    urlInput.value = '';
    currentVideoInfo = null;
    selectedFormatId = null;
    currentTaskId = null;
    videoCard.style.display = 'none';
    progressCard.style.display = 'none';
    completeCard.style.display = 'none';
    hideError();
    urlInput.focus();
});

// 粘贴自动解析
urlInput.addEventListener('paste', () => {
    setTimeout(() => {
        const val = urlInput.value.trim();
        if (val.startsWith('http://') || val.startsWith('https://')) {
            parseVideo();
        }
    }, 100);
});

// ─── AI 总结事件触发（追加，不修改已有逻辑） ──────
// 保存当前 URL 供 AI 总结使用
const _origShowVideoInfo = showVideoInfo;
showVideoInfo = function(info) {
    _origShowVideoInfo(info);
    currentVideoInfo = currentVideoInfo || {};
    currentVideoInfo.url = urlInput.value.trim();
};

// 在 newDownloadBtn 点击时触发 videoReset 事件
newDownloadBtn.addEventListener('click', function() {
    setTimeout(() => {
        document.dispatchEvent(new CustomEvent('videoReset'));
    }, 50);
});

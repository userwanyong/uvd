/**
 * AI 视频总结 - 前端逻辑
 * 依赖 app.js 中的全局变量: currentVideoInfo, showError
 * 依赖 markmap-view (CDN) 用于思维导图渲染
 */

(function () {
    'use strict';

    // ─── 状态 ────────────────────────────────────
    let aiTaskId = null;
    let aiPollTimer = null;
    let currentTab = 'summary';
    let mindmapInstance = null;

    // ─── 思维导图配色（暗色主题） ─────────────────
    const MINDMAP_COLORS = [
        '#f97316', '#3b82f6', '#a855f7', '#ef4444',
        '#22c55e', '#eab308', '#ec4899', '#06b6d4',
    ];

    // ─── DOM 引用 ────────────────────────────────
    const aiBtn = document.getElementById('aiSummaryBtn');
    const aiProgressCard = document.getElementById('aiProgressCard');
    const aiProgressLabel = document.getElementById('aiProgressLabel');
    const aiResultCard = document.getElementById('aiResultCard');
    const aiResultContent = document.getElementById('aiResultContent');
    const aiResultVideoTitle = document.getElementById('aiResultVideoTitle');
    const tabs = document.querySelectorAll('.ai-tab');

    // ─── 事件绑定 ────────────────────────────────

    if (aiBtn) {
        aiBtn.addEventListener('click', startAISummary);
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // 监听视频重置事件，清理 AI 状态
    document.addEventListener('videoReset', function () {
        if (aiProgressCard) aiProgressCard.style.display = 'none';
        if (aiResultCard) aiResultCard.style.display = 'none';
        destroyMindmap();
        resetAIState();
    });

    // ─── 核心函数 ────────────────────────────────

    async function startAISummary() {
        if (!currentVideoInfo || !currentVideoInfo.url) {
            showError('请先解析视频');
            return;
        }

        const url = typeof currentVideoInfo.url === 'string'
            ? currentVideoInfo.url
            : currentVideoInfo.url;

        // 重置状态
        resetAIState();
        aiBtn.disabled = true;
        aiBtn.textContent = '正在准备...';

        try {
            const resp = await fetch('/api/ai/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            const data = await resp.json();

            if (!resp.ok) {
                showError(data.detail || 'AI 总结启动失败');
                aiBtn.disabled = false;
                aiBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg> 生成视频总结';
                return;
            }

            aiTaskId = data.task_id;
            aiProgressCard.style.display = 'block';
            aiProgressLabel.textContent = '正在提取字幕文本...';

            // 开始轮询
            aiPollTimer = setInterval(pollAIProgress, 1500);

        } catch (err) {
            showError('网络错误，请重试');
            aiBtn.disabled = false;
            aiBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg> 生成视频总结';
        }
    }

    async function pollAIProgress() {
        if (!aiTaskId) return;

        try {
            const resp = await fetch(`/api/ai/progress/${aiTaskId}`);
            const data = await resp.json();

            if (!resp.ok) {
                clearInterval(aiPollTimer);
                showError(data.detail || '查询进度失败');
                return;
            }

            // 更新进度文本
            aiProgressLabel.textContent = data.progress || '处理中...';

            if (data.status === 'completed') {
                clearInterval(aiPollTimer);
                aiProgressCard.style.display = 'none';
                aiBtn.disabled = false;
                aiBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg> 重新生成总结';

                // 获取完整结果
                await fetchResult();
            } else if (data.status === 'error') {
                clearInterval(aiPollTimer);
                aiProgressCard.style.display = 'none';
                aiBtn.disabled = false;
                aiBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg> 生成视频总结';
                showError(data.error || 'AI 总结失败');
            }

        } catch (err) {
            // 轮询失败不中断，等下次重试
        }
    }

    async function fetchResult() {
        try {
            const resp = await fetch(`/api/ai/result/${aiTaskId}`);
            const data = await resp.json();

            if (!resp.ok) {
                showError(data.detail || '获取结果失败');
                return;
            }

            // 显示结果
            if (data.video_title && aiResultVideoTitle) {
                aiResultVideoTitle.textContent = data.video_title;
            }

            // 保存结果到内存
            window._aiResult = data.result;

            // 渲染默认 Tab
            switchTab('summary');
            aiResultCard.style.display = 'block';

        } catch (err) {
            showError('获取总结结果失败');
        }
    }

    function switchTab(tabName) {
        currentTab = tabName;

        // 更新 Tab 高亮
        tabs.forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tabName);
        });

        // 销毁上一个思维导图实例
        destroyMindmap();

        // 渲染内容
        const result = window._aiResult;
        if (!result || !aiResultContent) return;

        const contentMap = {
            summary: result.summary || '暂无总结内容',
            outline: result.outline || '暂无章节大纲',
            keypoints: result.key_points || '暂无核心要点',
            mindmap: result.mind_map || '暂无思维导图',
        };

        const raw = contentMap[tabName] || '';

        if (tabName === 'mindmap') {
            aiResultContent.className = 'ai-result-content mind-map';
            renderMindMapView(raw);
        } else {
            aiResultContent.className = 'ai-result-content';
            aiResultContent.innerHTML = renderMarkdown(raw);
        }
    }

    function resetAIState() {
        aiTaskId = null;
        currentTab = 'summary';
        window._aiResult = null;
        destroyMindmap();
        if (aiPollTimer) {
            clearInterval(aiPollTimer);
            aiPollTimer = null;
        }
    }

    function destroyMindmap() {
        if (mindmapInstance) {
            mindmapInstance.destroy();
            mindmapInstance = null;
        }
    }

    // ─── Markdown 渲染 ──────────────────────────

    function renderMarkdown(text) {
        if (!text) return '';

        let html = escapeHtml(text);

        // 二级标题 ## Title
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        // 三级标题 ### Title
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        // 加粗 **text**
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // 行内代码 `code`
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        // 无序列表 - item
        html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
        // 连续的 <li> 包裹为 <ul>
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
        // 有序列表 1. item
        html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
        // 引用 > text
        html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
        // 清理 <ul> 内部多余的换行
        html = html.replace(/(<\/li>)\n(<li>)/g, '$1$2');
        // 清理块级元素周围的换行
        html = html.replace(/\n*(<\/?(?:h[23]|ul|ol|blockquote)[^>]*>)\n*/g, '$1');
        // 清理开头的多余换行
        html = html.replace(/^\n+/, '');
        // 段落（双换行）
        html = html.replace(/\n\n+/g, '</p><p>');
        // 单换行
        html = html.replace(/\n/g, '<br>');

        // 包裹在 <p> 中
        if (!html.startsWith('<')) {
            html = '<p>' + html + '</p>';
        }
        // 清理空段落
        html = html.replace(/<p>\s*<\/p>/g, '');

        return html;
    }

    // ─── 思维导图：数据解析 ─────────────────────

    function parseMindMapTree(text) {
        if (!text) return [];
        const lines = text.split('\n');
        const root = { label: '', children: [] };
        const stack = [{ node: root, indent: -1 }];

        for (const rawLine of lines) {
            const match = rawLine.match(/^(\s*)[-*]\s+(.+)$/);
            if (!match) continue;

            const indent = match[1].length;
            const label = match[2].replace(/\*\*(.+?)\*\*/g, '$1').trim();
            const node = { label, children: [] };

            // 找到父节点
            while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
                stack.pop();
            }
            stack[stack.length - 1].node.children.push(node);
            stack.push({ node, indent });
        }

        // 如果第一行就是根节点，把它的 children 提升为根
        if (root.children.length === 1 && root.children[0].children.length > 0) {
            return root.children;
        }
        return root.children;
    }

    // ─── 思维导图：Markmap 渲染 ─────────────────

    function renderMindMapView(text) {
        const tree = parseMindMapTree(text);
        if (!tree.length) {
            aiResultContent.innerHTML = '<p style="color:var(--text-muted)">暂无思维导图数据</p>';
            return;
        }

        // 构建工具栏
        let html = '<div class="mindmap-toolbar">';
        html += '<span class="mindmap-toolbar-hint">滚轮缩放 · 拖拽平移</span>';
        html += '<div class="mindmap-toolbar-actions">';
        html += '<button class="btn-mindmap-dl" data-format="svg" title="下载 SVG 矢量图">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> SVG</button>';
        html += '<button class="btn-mindmap-dl" data-format="png" title="下载 PNG 图片">';
        html += '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> PNG</button>';
        html += '</div></div>';

        // 容器
        html += '<div class="mindmap-container" id="mindmapContainer"></div>';

        aiResultContent.innerHTML = html;

        // 绑定下载按钮
        aiResultContent.querySelectorAll('.btn-mindmap-dl').forEach(btn => {
            btn.addEventListener('click', () => {
                const fmt = btn.dataset.format;
                if (fmt === 'svg') downloadMindmapSVG();
                else if (fmt === 'png') downloadMindmapPNG();
            });
        });

        // 渲染
        const container = document.getElementById('mindmapContainer');
        if (window.markmap && window.markmap.Markmap) {
            renderWithMarkmap(container, tree);
        } else {
            // CDN 未加载时的降级：简单树形展示
            renderFallbackTree(container, tree);
        }
    }

    function renderWithMarkmap(container, tree) {
        // 将解析结果转换为 markmap 数据格式
        var rootData;
        if (tree.length === 1 && tree[0].children.length > 0) {
            rootData = convertNode(tree[0]);
        } else {
            rootData = {
                content: '思维导图',
                children: tree.map(function (n) { return convertNode(n); }),
            };
        }

        // 创建 SVG 元素
        var svgEl = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svgEl.style.width = '100%';
        svgEl.style.height = '100%';
        container.appendChild(svgEl);

        // 分支配色函数（暗色主题优化）
        // markmap 的 state.path 格式为 "1.2.3"，同一分支共享相同前缀
        var colorFn = function (node) {
            var s = node.state || {};
            var depth = s.depth || 0;
            var path = s.path || '';
            if (depth === 0) return '#00d4aa';
            var branchIdx = parseInt(path.split('.')[0], 10) || 0;
            return MINDMAP_COLORS[branchIdx % MINDMAP_COLORS.length];
        };

        // 使用 Markmap.create 静态方法创建实例
        var Markmap = window.markmap.Markmap;
        mindmapInstance = Markmap.create(svgEl, {
            color: colorFn,
            duration: 500,
            maxWidth: 220,
            paddingX: 16,
            // 注入暗色主题 CSS，确保导出 SVG/PNG 时文字颜色正确
            style: function (id) {
                return [
                    '.markmap {',
                    '  --markmap-text-color: #e0e0f0;',
                    '  --markmap-code-bg: rgba(255,255,255,0.06);',
                    '  --markmap-code-color: #00d4aa;',
                    '  --markmap-circle-open-bg: rgba(255,255,255,0.15);',
                    '  --markmap-highlight-bg: rgba(0,212,170,0.3);',
                    '  --markmap-a-color: #00d4aa;',
                    '  --markmap-a-hover-color: #33e0be;',
                    '  color: #e0e0f0;',
                    '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;',
                    '}',
                ].join('\n');
            },
        }, rootData);

        // 渲染完成后自适应视图
        setTimeout(function () {
            if (mindmapInstance && mindmapInstance.fit) {
                mindmapInstance.fit();
            }
        }, 800);
    }

    function convertNode(node) {
        return {
            content: node.label,
            children: (node.children || []).map(function (c) {
                return convertNode(c);
            }),
        };
    }

    // ─── 思维导图：降级渲染（CDN 不可用时） ─────

    function renderFallbackTree(container, tree) {
        container.classList.add('mindmap-fallback');
        let html = '';
        tree.forEach(function (node) {
            html += renderFallbackNode(node, true);
        });
        container.innerHTML = html;
    }

    function renderFallbackNode(node, isRoot) {
        let html = '<div class="fallback-node">';
        html += '<div class="fallback-label' + (isRoot ? ' root' : '') + '">' + escapeHtml(node.label) + '</div>';
        if (node.children && node.children.length > 0) {
            html += '<div class="fallback-children">';
            node.children.forEach(function (child) {
                html += renderFallbackNode(child, false);
            });
            html += '</div>';
        }
        html += '</div>';
        return html;
    }

    // ─── 思维导图：下载功能 ─────────────────────

    // 暗色主题内联 CSS，用于注入导出的 SVG 确保文字颜色正确
    var DARK_THEME_CSS = [
        '.markmap {',
        '  --markmap-text-color: #e0e0f0;',
        '  --markmap-code-bg: rgba(255,255,255,0.06);',
        '  --markmap-code-color: #00d4aa;',
        '  --markmap-circle-open-bg: rgba(255,255,255,0.15);',
        '  --markmap-highlight-bg: rgba(0,212,170,0.3);',
        '  --markmap-a-color: #00d4aa;',
        '  --markmap-a-hover-color: #33e0be;',
        '  color: #e0e0f0;',
        '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;',
        '}',
    ].join('\n');

    function getMindmapSVG() {
        var container = document.getElementById('mindmapContainer');
        if (!container) return null;
        return container.querySelector('svg');
    }

    function injectDarkStyles(svgClone) {
        // 在克隆的 SVG 中注入暗色主题样式，确保导出时颜色正确
        var existingStyle = svgClone.querySelector('style');
        if (existingStyle) {
            existingStyle.textContent += '\n' + DARK_THEME_CSS;
        } else {
            var styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style');
            styleEl.textContent = DARK_THEME_CSS;
            svgClone.insertBefore(styleEl, svgClone.firstChild);
        }
        // 对所有 foreignObject 内的 div 直接设置内联样式（双重保障）
        svgClone.querySelectorAll('.markmap-foreign > div > div').forEach(function (div) {
            div.style.color = '#e0e0f0';
            div.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif';
        });
    }

    function downloadMindmapSVG() {
        var svgEl = getMindmapSVG();
        if (!svgEl) return;

        // 克隆 SVG
        var clone = svgEl.cloneNode(true);
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

        // 注入暗色主题样式
        injectDarkStyles(clone);

        // 插入暗色背景
        var bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        bg.setAttribute('width', '100%');
        bg.setAttribute('height', '100%');
        bg.setAttribute('fill', '#16162a');
        clone.insertBefore(bg, clone.firstChild.nextSibling);

        var svgData = new XMLSerializer().serializeToString(clone);
        var blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
        var url = URL.createObjectURL(blob);

        var a = document.createElement('a');
        a.href = url;
        var title = (aiResultVideoTitle && aiResultVideoTitle.textContent) || 'mindmap';
        a.download = title + '.svg';
        a.click();

        setTimeout(function () { URL.revokeObjectURL(url); }, 100);
    }

    function downloadMindmapPNG() {
        var svgEl = getMindmapSVG();
        if (!svgEl) return;

        // 获取内容范围
        var bbox = svgEl.getBBox();
        var padding = 40;
        var width = Math.max(bbox.width + padding * 2, 800);
        var height = Math.max(bbox.height + padding * 2, 500);

        // 克隆 SVG 并设置尺寸
        var clone = svgEl.cloneNode(true);
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        clone.setAttribute('width', width);
        clone.setAttribute('height', height);

        // 设置 viewBox
        clone.setAttribute('viewBox', (bbox.x - padding) + ' ' + (bbox.y - padding) + ' ' + width + ' ' + height);

        // 注入暗色主题样式
        injectDarkStyles(clone);

        // 插入暗色背景
        var bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        bg.setAttribute('x', bbox.x - padding);
        bg.setAttribute('y', bbox.y - padding);
        bg.setAttribute('width', width);
        bg.setAttribute('height', height);
        bg.setAttribute('fill', '#16162a');
        clone.insertBefore(bg, clone.firstChild.nextSibling);

        // 转为 Base64 Data URL
        var svgData = new XMLSerializer().serializeToString(clone);
        var svgBase64 = btoa(unescape(encodeURIComponent(svgData)));
        var imgSrc = 'data:image/svg+xml;base64,' + svgBase64;

        var img = new Image();
        img.onload = function () {
            var scale = 2; // 2x 高清
            var canvas = document.createElement('canvas');
            canvas.width = width * scale;
            canvas.height = height * scale;
            var ctx = canvas.getContext('2d');
            ctx.scale(scale, scale);
            ctx.fillStyle = '#16162a';
            ctx.fillRect(0, 0, width, height);
            ctx.drawImage(img, 0, 0, width, height);

            var a = document.createElement('a');
            var title = (aiResultVideoTitle && aiResultVideoTitle.textContent) || 'mindmap';
            a.download = title + '.png';
            a.href = canvas.toDataURL('image/png');
            a.click();
        };
        img.src = imgSrc;
    }

    // ─── 工具函数 ────────────────────────────────

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

})();

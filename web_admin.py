from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from db import connection, get_int_setting, get_setting
from init_db import init_db


RULE_TYPES = {"cut_after", "remove_keyword", "regex", "drop_if_keyword"}


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TG Forwarder Admin</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1d2433;
      --muted: #667085;
      --line: #d9dee7;
      --primary: #0f766e;
      --primary-dark: #115e59;
      --danger: #b42318;
      --danger-bg: #fff1f0;
      --ok-bg: #ecfdf3;
      --warn-bg: #fffaeb;
      --shadow: 0 1px 2px rgba(16, 24, 40, .06), 0 1px 3px rgba(16, 24, 40, .08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }

    header {
      position: sticky;
      top: 0;
      z-index: 2;
      background: rgba(255, 255, 255, .94);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(10px);
    }

    .bar {
      max-width: 1240px;
      margin: 0 auto;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }

    main {
      max-width: 1240px;
      margin: 0 auto;
      padding: 20px;
      display: grid;
      gap: 18px;
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(360px, .9fr);
      gap: 18px;
      align-items: start;
    }

    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .section-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 650;
    }

    .body {
      padding: 16px;
    }

    form {
      display: grid;
      gap: 12px;
    }

    .fields {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .fields.three {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
    }

    input, select, textarea {
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      color: var(--text);
      background: #fff;
      font: inherit;
    }

    textarea {
      min-height: 76px;
      resize: vertical;
    }

    input[type="checkbox"] {
      width: 16px;
      min-height: 16px;
      accent-color: var(--primary);
    }

    .checks {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      align-items: center;
    }

    .check {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      color: var(--text);
      font-size: 13px;
    }

    button {
      border: 1px solid transparent;
      border-radius: 6px;
      min-height: 36px;
      padding: 7px 12px;
      cursor: pointer;
      font: inherit;
      font-weight: 600;
    }

    .primary {
      background: var(--primary);
      color: #fff;
    }

    .primary:hover { background: var(--primary-dark); }

    .ghost {
      background: #fff;
      border-color: var(--line);
      color: var(--text);
    }

    .danger {
      background: var(--danger-bg);
      color: var(--danger);
      border-color: #ffd2cc;
    }

    .toolbar {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      background: #fbfcfe;
      font-size: 12px;
      font-weight: 650;
    }

    tr:last-child td { border-bottom: 0; }

    .id {
      font-family: Consolas, "Cascadia Mono", monospace;
      white-space: nowrap;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      background: var(--ok-bg);
      color: #067647;
      font-size: 12px;
      font-weight: 650;
    }

    .pill.off {
      background: var(--warn-bg);
      color: #93370d;
    }

    .muted { color: var(--muted); }

    .notice {
      min-height: 36px;
      display: flex;
      align-items: center;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--muted);
    }

    .notice.error {
      background: var(--danger-bg);
      color: var(--danger);
      border-color: #ffd2cc;
    }

    .empty {
      padding: 18px;
      color: var(--muted);
      text-align: center;
    }

    .docs {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .doc-item {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      background: #fbfcfe;
    }

    .doc-item code {
      display: inline-block;
      margin-bottom: 4px;
      font-family: Consolas, "Cascadia Mono", monospace;
      font-weight: 650;
      color: var(--primary-dark);
    }

    .doc-item p {
      margin: 0;
      color: var(--muted);
    }

    @media (max-width: 900px) {
      .grid, .fields, .fields.three, .docs {
        grid-template-columns: 1fr;
      }

      .bar {
        align-items: flex-start;
        flex-direction: column;
      }

      table {
        display: block;
        overflow-x: auto;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="bar">
      <h1>TG Forwarder Admin</h1>
      <div class="toolbar">
        <button class="ghost" id="refreshBtn" type="button">刷新</button>
      </div>
    </div>
  </header>

  <main>
    <div id="notice" class="notice">正在加载配置...</div>

    <div class="grid">
      <section>
        <div class="section-head">
          <h2>来源频道</h2>
        </div>
        <div class="body">
          <form id="channelForm">
            <div class="fields three">
              <label>频道 ID
                <input name="channel_id" placeholder="-100xxxxxxxxxx" required>
              </label>
              <label>频道名称
                <input name="channel_name" placeholder="例如：缅甸新闻">
              </label>
              <label>默认分类
                <select name="default_type" id="channelDefaultType">
                  <option value="auto">auto</option>
                </select>
              </label>
            </div>
            <div class="fields three">
              <label>优先级
                <input name="priority" type="number" value="50">
              </label>
              <label class="check">
                <input name="enabled" type="checkbox" checked> 启用监听
              </label>
              <label class="check">
                <input name="keep_media" type="checkbox" checked> 保留媒体
              </label>
            </div>
            <div class="checks">
              <label class="check">
                <input name="remove_urls" type="checkbox" checked> 清理链接和 @
              </label>
            </div>
            <div class="toolbar">
              <button class="primary" type="submit">保存频道</button>
            </div>
          </form>
        </div>
        <div id="channelsTable"></div>
      </section>

      <section>
        <div class="section-head">
          <h2>目标频道</h2>
        </div>
        <div class="body">
          <form id="targetForm">
            <div class="fields">
              <label>类型
                <select name="type" id="targetType"></select>
              </label>
              <label>目标频道 ID
                <input name="target_channel_id" placeholder="-100xxxxxxxxxx" required>
              </label>
            </div>
            <div class="checks">
              <label class="check">
                <input name="enabled" type="checkbox" checked> 启用
              </label>
            </div>
            <div class="toolbar">
              <button class="primary" type="submit">保存目标</button>
            </div>
          </form>
        </div>
        <div id="targetsTable"></div>
      </section>
    </div>

    <section>
      <div class="section-head">
        <h2>自定义分类</h2>
      </div>
      <div class="body">
        <form id="categoryForm">
          <div class="fields three">
            <label>分类标识
              <input name="name" placeholder="例如：life、crime、business" required>
            </label>
            <label>显示名称
              <input name="label" placeholder="例如：生活、犯罪、商业">
            </label>
            <label>优先级
              <input name="priority" type="number" value="50">
            </label>
          </div>
          <div class="checks">
            <label class="check">
              <input name="enabled" type="checkbox" checked> 启用分类
            </label>
          </div>
          <div class="toolbar">
            <button class="primary" type="submit">保存分类</button>
          </div>
        </form>
      </div>
      <div id="categoriesTable"></div>
    </section>

    <section>
      <div class="section-head">
        <h2>系统参数</h2>
      </div>
      <div class="body">
        <form id="settingForm">
          <div class="fields three">
            <label>参数名
              <input name="key" placeholder="例如：config_refresh_seconds" required>
            </label>
            <label>参数值
              <input name="value" placeholder="例如：10" required>
            </label>
            <label>说明
              <input name="description" placeholder="可选">
            </label>
          </div>
          <div class="toolbar">
            <button class="primary" type="submit">保存参数</button>
          </div>
        </form>
      </div>
      <div id="settingsTable"></div>
    </section>

    <section>
      <div class="section-head">
        <h2>广告 / 清洗规则</h2>
      </div>
      <div class="body">
        <form id="ruleForm">
          <div class="fields three">
            <label>来源频道
              <select name="channel_id" id="ruleChannel"></select>
            </label>
            <label>规则类型
              <select name="rule_type">
                <option value="cut_after">cut_after</option>
                <option value="remove_keyword">remove_keyword</option>
                <option value="regex">regex</option>
                <option value="drop_if_keyword">drop_if_keyword</option>
              </select>
            </label>
            <label>优先级
              <input name="priority" type="number" value="80">
            </label>
          </div>
          <label>规则内容
            <textarea name="rule_value" placeholder="例如：✍️商务-广告合作： 或 https?://\\S+" required></textarea>
          </label>
          <div class="checks">
            <label class="check">
              <input name="enabled" type="checkbox" checked> 启用规则
            </label>
          </div>
          <div class="toolbar">
            <button class="primary" type="submit">新增规则</button>
          </div>
        </form>
      </div>
      <div id="rulesTable"></div>
    </section>

    <section>
      <div class="section-head">
        <h2>信息分类规则</h2>
      </div>
      <div class="body">
        <form id="classifyForm">
          <div class="fields three">
            <label>关键词
              <input name="keyword" placeholder="例如：警方、投稿、爆料" required>
            </label>
            <label>分类
              <select name="category" id="classifyCategory"></select>
            </label>
            <label>权重
              <input name="weight" type="number" value="80">
            </label>
          </div>
          <div class="checks">
            <label class="check">
              <input name="enabled" type="checkbox" checked> 启用规则
            </label>
          </div>
          <div class="toolbar">
            <button class="primary" type="submit">新增分类规则</button>
          </div>
        </form>
      </div>
      <div id="classifyTable"></div>
    </section>

    <section>
      <div class="section-head">
        <h2>规则说明</h2>
      </div>
      <div class="body">
        <div class="docs">
          <div class="doc-item">
            <code>auto</code>
            <p>频道默认分类为 auto 时，系统会根据“信息分类规则”的关键词判断发往某个自定义分类。</p>
          </div>
          <div class="doc-item">
            <code>分类标识</code>
            <p>自定义分类的英文或拼音代号，例如 life、crime、business。目标频道和分类规则会使用这个标识。</p>
          </div>
          <div class="doc-item">
            <code>目标频道类型</code>
            <p>每个分类都可以配置自己的目标频道。消息被分到该分类后，会转发到同名目标频道。</p>
          </div>
          <div class="doc-item">
            <code>news / post</code>
            <p>news 和 post 是默认内置分类，也可以继续新增更多分类来做多频道分流。</p>
          </div>
          <div class="doc-item">
            <code>cut_after</code>
            <p>从命中的文字开始，把后面的所有内容删除。适合清理尾部投稿、商务广告、博彩链接。</p>
          </div>
          <div class="doc-item">
            <code>remove_keyword</code>
            <p>只删除命中的固定文字，保留前后正文。适合删除“广告合作”“商务合作”等短词。</p>
          </div>
          <div class="doc-item">
            <code>regex</code>
            <p>使用正则表达式删除匹配内容，例如 https?://\S+ 可以删除链接。</p>
          </div>
          <div class="doc-item">
            <code>drop_if_keyword</code>
            <p>只要消息包含该关键词，整条消息都不转发。适合完全过滤广告、招聘、博彩类消息。</p>
          </div>
          <div class="doc-item">
            <code>优先级</code>
            <p>数字越大越先执行。清洗规则建议尾部截断设高一点，普通删除和正则设低一点。</p>
          </div>
          <div class="doc-item">
            <code>分类权重</code>
            <p>数字越大越先匹配。比如“投稿”权重 100 高于“新闻”70 时，含投稿的消息会优先归为 post。</p>
          </div>
          <div class="doc-item">
            <code>remove_urls</code>
            <p>频道开启后，会额外清理 http 链接、t.me 链接和 @用户名。</p>
          </div>
          <div class="doc-item">
            <code>keep_media</code>
            <p>开启后转发图片、视频、文件等媒体；关闭后只发送清洗后的文本。</p>
          </div>
          <div class="doc-item">
            <code>config_refresh_seconds</code>
            <p>主程序定时刷新频道、目标频道和系统参数的间隔秒数。保存后会在下一轮刷新时生效。</p>
          </div>
          <div class="doc-item">
            <code>web_host / web_port</code>
            <p>Web 后台监听地址和端口。修改后需要下次启动 Web 服务时生效。</p>
          </div>
        </div>
      </div>
    </section>
  </main>

  <script>
    const state = { categories: [], channels: [], targets: [], settings: [], clean_rules: [], classify_rules: [] };
    const notice = document.querySelector("#notice");

    function setNotice(text, error = false) {
      notice.textContent = text;
      notice.classList.toggle("error", error);
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
      }
      return data;
    }

    function formData(form) {
      const data = Object.fromEntries(new FormData(form).entries());
      for (const el of form.querySelectorAll("input[type=checkbox]")) {
        data[el.name] = el.checked ? 1 : 0;
      }
      return data;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function statusPill(enabled) {
      return enabled ? '<span class="pill">启用</span>' : '<span class="pill off">停用</span>';
    }

    function renderChannels() {
      const host = document.querySelector("#channelsTable");
      if (!state.channels.length) {
        host.innerHTML = '<div class="empty">暂无来源频道</div>';
        return;
      }
      host.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>频道</th><th>默认分类</th><th>媒体/链接</th><th>状态</th><th></th>
            </tr>
          </thead>
          <tbody>
            ${state.channels.map(row => `
              <tr>
                <td>
                  <div class="id">${escapeHtml(row.channel_id)}</div>
                  <div>${escapeHtml(row.channel_name || "")}</div>
                </td>
                <td>${escapeHtml(row.default_type)}</td>
                <td>
                  <div>媒体：${row.keep_media ? "保留" : "不保留"}</div>
                  <div>链接：${row.remove_urls ? "清理" : "保留"}</div>
                </td>
                <td>${statusPill(row.enabled)}</td>
                <td><button class="danger" data-delete-channel="${escapeHtml(row.channel_id)}" type="button">删除</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }

    function renderTargets() {
      const host = document.querySelector("#targetsTable");
      if (!state.targets.length) {
        host.innerHTML = '<div class="empty">暂无目标频道</div>';
        return;
      }
      host.innerHTML = `
        <table>
          <thead>
            <tr><th>类型</th><th>目标频道 ID</th><th>状态</th></tr>
          </thead>
          <tbody>
            ${state.targets.map(row => `
              <tr>
                <td>${escapeHtml(row.type)}</td>
                <td class="id">${escapeHtml(row.target_channel_id)}</td>
                <td>${statusPill(row.enabled)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }

    function renderCategories() {
      const host = document.querySelector("#categoriesTable");
      if (!state.categories.length) {
        host.innerHTML = '<div class="empty">暂无分类</div>';
        return;
      }
      host.innerHTML = `
        <table>
          <thead>
            <tr><th>分类</th><th>显示名称</th><th>优先级</th><th>状态</th><th></th></tr>
          </thead>
          <tbody>
            ${state.categories.map(row => `
              <tr>
                <td class="id">${escapeHtml(row.name)}</td>
                <td>${escapeHtml(row.label || "")}</td>
                <td>${escapeHtml(row.priority)}</td>
                <td>${statusPill(row.enabled)}</td>
                <td><button class="danger" data-delete-category="${escapeHtml(row.name)}" type="button">删除</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }

    function renderSettings() {
      const host = document.querySelector("#settingsTable");
      if (!state.settings.length) {
        host.innerHTML = '<div class="empty">暂无系统参数</div>';
        return;
      }
      host.innerHTML = `
        <table>
          <thead>
            <tr><th>参数名</th><th>参数值</th><th>说明</th><th>更新时间</th></tr>
          </thead>
          <tbody>
            ${state.settings.map(row => `
              <tr>
                <td class="id">${escapeHtml(row.key)}</td>
                <td>${escapeHtml(row.value)}</td>
                <td>${escapeHtml(row.description || "")}</td>
                <td>${escapeHtml(row.updated_at || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }

    function renderRules() {
      const host = document.querySelector("#rulesTable");
      if (!state.clean_rules.length) {
        host.innerHTML = '<div class="empty">暂无清洗规则</div>';
        return;
      }
      host.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>频道 ID</th><th>类型</th><th>内容</th><th>优先级</th><th>状态</th><th></th>
            </tr>
          </thead>
          <tbody>
            ${state.clean_rules.map(row => `
              <tr>
                <td class="id">${escapeHtml(row.channel_id)}</td>
                <td>${escapeHtml(row.rule_type)}</td>
                <td>${escapeHtml(row.rule_value)}</td>
                <td>${escapeHtml(row.priority)}</td>
                <td>${statusPill(row.enabled)}</td>
                <td><button class="danger" data-delete-rule="${row.id}" type="button">删除</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }

    function renderClassifyRules() {
      const host = document.querySelector("#classifyTable");
      if (!state.classify_rules.length) {
        host.innerHTML = '<div class="empty">暂无分类规则</div>';
        return;
      }
      host.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>关键词</th><th>分类</th><th>权重</th><th>状态</th><th></th>
            </tr>
          </thead>
          <tbody>
            ${state.classify_rules.map(row => `
              <tr>
                <td>${escapeHtml(row.keyword)}</td>
                <td>${escapeHtml(row.category)}</td>
                <td>${escapeHtml(row.weight)}</td>
                <td>${statusPill(row.enabled)}</td>
                <td><button class="danger" data-delete-classify="${row.id}" type="button">删除</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>`;
    }

    function renderRuleChannels() {
      const select = document.querySelector("#ruleChannel");
      select.innerHTML = state.channels.map(row => {
        const label = `${row.channel_id} ${row.channel_name || ""}`.trim();
        return `<option value="${escapeHtml(row.channel_id)}">${escapeHtml(label)}</option>`;
      }).join("");
    }

    function renderCategoryOptions() {
      const categoryOptions = state.categories
        .filter(row => row.enabled)
        .map(row => {
          const label = row.label ? `${row.name} - ${row.label}` : row.name;
          return `<option value="${escapeHtml(row.name)}">${escapeHtml(label)}</option>`;
        })
        .join("");

      document.querySelector("#channelDefaultType").innerHTML =
        `<option value="auto">auto</option>${categoryOptions}`;
      document.querySelector("#targetType").innerHTML = categoryOptions;
      document.querySelector("#classifyCategory").innerHTML = categoryOptions;
    }

    async function loadAll() {
      const data = await api("/api/state");
      Object.assign(state, data);
      renderCategoryOptions();
      renderChannels();
      renderTargets();
      renderCategories();
      renderSettings();
      renderRuleChannels();
      renderRules();
      renderClassifyRules();
      setNotice("配置已加载。主程序会定时读取最新配置，不需要为了修改规则而停止转发。");
    }

    document.querySelector("#refreshBtn").addEventListener("click", () => {
      loadAll().catch(err => setNotice(err.message, true));
    });

    document.querySelector("#channelForm").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await api("/api/channels", {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        form.reset();
        form.enabled.checked = true;
        form.keep_media.checked = true;
        form.remove_urls.checked = true;
        await loadAll();
        setNotice("频道已保存。");
      } catch (err) {
        setNotice(err.message, true);
      }
    });

    document.querySelector("#targetForm").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await api("/api/targets", {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        await loadAll();
        setNotice("目标频道已保存。");
      } catch (err) {
        setNotice(err.message, true);
      }
    });

    document.querySelector("#categoryForm").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await api("/api/categories", {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        form.reset();
        form.enabled.checked = true;
        await loadAll();
        setNotice("分类已保存。");
      } catch (err) {
        setNotice(err.message, true);
      }
    });

    document.querySelector("#settingForm").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await api("/api/settings", {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        form.reset();
        await loadAll();
        setNotice("系统参数已保存。");
      } catch (err) {
        setNotice(err.message, true);
      }
    });

    document.querySelector("#ruleForm").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await api("/api/clean-rules", {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        form.rule_value.value = "";
        await loadAll();
        setNotice("清洗规则已新增。");
      } catch (err) {
        setNotice(err.message, true);
      }
    });

    document.querySelector("#classifyForm").addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        await api("/api/classify-rules", {
          method: "POST",
          body: JSON.stringify(formData(form)),
        });
        form.keyword.value = "";
        await loadAll();
        setNotice("分类规则已新增。");
      } catch (err) {
        setNotice(err.message, true);
      }
    });

    document.body.addEventListener("click", async event => {
      const channelId = event.target.dataset.deleteChannel;
      const ruleId = event.target.dataset.deleteRule;
      const classifyId = event.target.dataset.deleteClassify;
      const categoryName = event.target.dataset.deleteCategory;
      try {
        if (channelId) {
          if (!confirm(`删除来源频道 ${channelId}？相关清洗规则也会删除。`)) return;
          await api(`/api/channels/${encodeURIComponent(channelId)}`, { method: "DELETE" });
          await loadAll();
          setNotice("频道已删除。");
        }
        if (ruleId) {
          if (!confirm("删除这条清洗规则？")) return;
          await api(`/api/clean-rules/${ruleId}`, { method: "DELETE" });
          await loadAll();
          setNotice("规则已删除。");
        }
        if (classifyId) {
          if (!confirm("删除这条分类规则？")) return;
          await api(`/api/classify-rules/${classifyId}`, { method: "DELETE" });
          await loadAll();
          setNotice("分类规则已删除。");
        }
        if (categoryName) {
          if (!confirm(`删除分类 ${categoryName}？请先移除引用它的目标频道、频道默认分类和分类规则。`)) return;
          await api(`/api/categories/${encodeURIComponent(categoryName)}`, { method: "DELETE" });
          await loadAll();
          setNotice("分类已删除。");
        }
      } catch (err) {
        setNotice(err.message, true);
      }
    });

    loadAll().catch(err => setNotice(err.message, true));
  </script>
</body>
</html>
"""


def as_bool(value) -> int:
    return 1 if str(value).lower() in {"1", "true", "yes", "on"} else 0


def require_text(data: dict, key: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} 不能为空")
    return value


def int_value(data: dict, key: str, default: int) -> int:
    value = data.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def list_state() -> dict:
    with connection() as conn:
        categories = conn.execute(
            """
            SELECT name, label, enabled, priority
            FROM categories
            ORDER BY priority DESC, name ASC
            """
        ).fetchall()
        channels = conn.execute(
            """
            SELECT id, channel_id, channel_name, enabled, priority, default_type, keep_media, remove_urls
            FROM channels
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()
        targets = conn.execute(
            """
            SELECT id, type, target_channel_id, enabled
            FROM targets
            ORDER BY type ASC
            """
        ).fetchall()
        settings = conn.execute(
            """
            SELECT key, value, description, updated_at
            FROM settings
            ORDER BY key ASC
            """
        ).fetchall()
        clean_rules = conn.execute(
            """
            SELECT id, channel_id, rule_type, rule_value, priority, enabled
            FROM clean_rules
            ORDER BY channel_id ASC, priority DESC, id ASC
            """
        ).fetchall()
        classify_rules = conn.execute(
            """
            SELECT id, keyword, category, weight, enabled
            FROM classify_rules
            ORDER BY weight DESC, id ASC
            """
        ).fetchall()
    return {
        "categories": [dict(row) for row in categories],
        "channels": [dict(row) for row in channels],
        "targets": [dict(row) for row in targets],
        "settings": [dict(row) for row in settings],
        "clean_rules": [dict(row) for row in clean_rules],
        "classify_rules": [dict(row) for row in classify_rules],
    }


def category_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM categories WHERE name = ?",
            (name,),
        ).fetchone()
    )


def upsert_category(data: dict) -> dict:
    name = require_text(data, "name")
    if name == "auto":
        raise ValueError("auto 是系统保留值，不能作为分类标识")
    label = str(data.get("label", "")).strip() or name

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO categories (name, label, enabled, priority)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                label = excluded.label,
                enabled = excluded.enabled,
                priority = excluded.priority,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                name,
                label,
                as_bool(data.get("enabled", 1)),
                int_value(data, "priority", 50),
            ),
        )
    return {"ok": True}


def delete_category(name: str) -> dict:
    with connection() as conn:
        checks = [
            (
                "目标频道",
                conn.execute("SELECT 1 FROM targets WHERE type = ?", (name,)).fetchone(),
            ),
            (
                "频道默认分类",
                conn.execute("SELECT 1 FROM channels WHERE default_type = ?", (name,)).fetchone(),
            ),
            (
                "分类规则",
                conn.execute("SELECT 1 FROM classify_rules WHERE category = ?", (name,)).fetchone(),
            ),
            (
                "转发记录",
                conn.execute("SELECT 1 FROM forwarded_messages WHERE category = ?", (name,)).fetchone(),
            ),
        ]
        used_by = [label for label, row in checks if row]
        if used_by:
            raise ValueError(f"分类正在被使用，不能删除：{', '.join(used_by)}")

        conn.execute("DELETE FROM categories WHERE name = ?", (name,))
    return {"ok": True}


def upsert_setting(data: dict) -> dict:
    key = require_text(data, "key")
    value = require_text(data, "value")
    description = str(data.get("description", "")).strip()

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value, description)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                description = excluded.description,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value, description),
        )
    return {"ok": True}


def upsert_channel(data: dict) -> dict:
    channel_id = require_text(data, "channel_id")
    default_type = str(data.get("default_type", "auto")).strip()

    with connection() as conn:
        if default_type != "auto" and not category_exists(conn, default_type):
            raise ValueError("default_type 必须是 auto 或已存在的自定义分类")

        conn.execute(
            """
            INSERT INTO channels (
                channel_id,
                channel_name,
                enabled,
                priority,
                default_type,
                keep_media,
                remove_urls
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                channel_name = excluded.channel_name,
                enabled = excluded.enabled,
                priority = excluded.priority,
                default_type = excluded.default_type,
                keep_media = excluded.keep_media,
                remove_urls = excluded.remove_urls,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                channel_id,
                str(data.get("channel_name", "")).strip(),
                as_bool(data.get("enabled", 1)),
                int_value(data, "priority", 50),
                default_type,
                as_bool(data.get("keep_media", 1)),
                as_bool(data.get("remove_urls", 1)),
            ),
        )
    return {"ok": True}


def delete_channel(channel_id: str) -> dict:
    with connection() as conn:
        conn.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    return {"ok": True}


def upsert_target(data: dict) -> dict:
    target_type = require_text(data, "type")
    target_channel_id = require_text(data, "target_channel_id")

    with connection() as conn:
        if not category_exists(conn, target_type):
            raise ValueError("type 必须是已存在的自定义分类")

        conn.execute(
            """
            INSERT INTO targets (type, target_channel_id, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(type) DO UPDATE SET
                target_channel_id = excluded.target_channel_id,
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (target_type, target_channel_id, as_bool(data.get("enabled", 1))),
        )
    return {"ok": True}


def create_clean_rule(data: dict) -> dict:
    channel_id = require_text(data, "channel_id")
    rule_type = require_text(data, "rule_type")
    if rule_type not in RULE_TYPES:
        raise ValueError("rule_type 不合法")
    rule_value = require_text(data, "rule_value")

    with connection() as conn:
        channel = conn.execute(
            "SELECT 1 FROM channels WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        if not channel:
            raise ValueError("来源频道不存在")

        conn.execute(
            """
            INSERT INTO clean_rules (channel_id, rule_type, rule_value, priority, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                channel_id,
                rule_type,
                rule_value,
                int_value(data, "priority", 50),
                as_bool(data.get("enabled", 1)),
            ),
        )
    return {"ok": True}


def delete_clean_rule(rule_id: int) -> dict:
    with connection() as conn:
        conn.execute("DELETE FROM clean_rules WHERE id = ?", (rule_id,))
    return {"ok": True}


def create_classify_rule(data: dict) -> dict:
    keyword = require_text(data, "keyword")
    category = require_text(data, "category")

    with connection() as conn:
        if not category_exists(conn, category):
            raise ValueError("category 必须是已存在的自定义分类")

        conn.execute(
            """
            INSERT INTO classify_rules (keyword, category, weight, enabled)
            VALUES (?, ?, ?, ?)
            """,
            (
                keyword,
                category,
                int_value(data, "weight", 50),
                as_bool(data.get("enabled", 1)),
            ),
        )
    return {"ok": True}


def delete_classify_rule(rule_id: int) -> dict:
    with connection() as conn:
        conn.execute("DELETE FROM classify_rules WHERE id = ?", (rule_id,))
    return {"ok": True}


class AdminHandler(BaseHTTPRequestHandler):
    server_version = "TGForwarderAdmin/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, error: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self.send_json({"error": error}, status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(HTML)
            return
        if parsed.path == "/api/state":
            self.send_json(list_state())
            return
        self.send_error_json("Not found", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            data = self.read_json()
            if parsed.path == "/api/categories":
                self.send_json(upsert_category(data))
                return
            if parsed.path == "/api/settings":
                self.send_json(upsert_setting(data))
                return
            if parsed.path == "/api/channels":
                self.send_json(upsert_channel(data))
                return
            if parsed.path == "/api/targets":
                self.send_json(upsert_target(data))
                return
            if parsed.path == "/api/clean-rules":
                self.send_json(create_clean_rule(data))
                return
            if parsed.path == "/api/classify-rules":
                self.send_json(create_classify_rule(data))
                return
            self.send_error_json("Not found", HTTPStatus.NOT_FOUND)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error_json(str(exc))
        except Exception as exc:
            self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/categories/"):
                name = parsed.path.removeprefix("/api/categories/")
                name = parse_qs(f"x={name}")["x"][0]
                self.send_json(delete_category(name))
                return
            if parsed.path.startswith("/api/channels/"):
                channel_id = parsed.path.removeprefix("/api/channels/")
                channel_id = parse_qs(f"x={channel_id}")["x"][0]
                self.send_json(delete_channel(channel_id))
                return
            if parsed.path.startswith("/api/clean-rules/"):
                rule_id = int(parsed.path.removeprefix("/api/clean-rules/"))
                self.send_json(delete_clean_rule(rule_id))
                return
            if parsed.path.startswith("/api/classify-rules/"):
                rule_id = int(parsed.path.removeprefix("/api/classify-rules/"))
                self.send_json(delete_classify_rule(rule_id))
                return
            self.send_error_json("Not found", HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_error_json(str(exc))
        except Exception as exc:
            self.send_error_json(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)


def create_server(host: str, port: int, *, initialize: bool = True) -> ThreadingHTTPServer:
    if initialize:
        init_db()
    return ThreadingHTTPServer((host, port), AdminHandler)


def serve_server(server: ThreadingHTTPServer) -> None:
    host, port = server.server_address[:2]
    print(f"Web 管理端已启动: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Web 管理端已停止")
    finally:
        server.server_close()


def run(host: str, port: int, *, initialize: bool = True) -> None:
    serve_server(create_server(host, port, initialize=initialize))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    init_db()
    run(
        args.host or get_setting("web_host", "127.0.0.1") or "127.0.0.1",
        args.port if args.port is not None else get_int_setting("web_port", 8080),
        initialize=False,
    )

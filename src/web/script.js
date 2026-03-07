const AGENT_COUNT_EL = document.getElementById('agent-count');
const UPTIME_EL = document.getElementById('uptime');
const FLOOR_EL = document.getElementById('agent-layer');
const LOG_CONTENT_EL = document.getElementById('log-content');
const CLOCK_EL = document.getElementById('clock');

let agentsData = {};
let startTime = Date.now();

// エージェントの役職ごとの色と初期位置
const AGENT_CONFIG = {
    "pm": { color: "#ff4b2b", icon: "👔" },
    "dev": { color: "#45cafc", icon: "💻" },
    "browser": { color: "#ff9a9e", icon: "🌐" },
    "analyst": { color: "#a18cd1", icon: "📊" },
    "default": { color: "#e94560", icon: "🤖" }
};

// オフィスの重要地点
const LOCATIONS = {
    idle: [
        { x: 20, y: 70 }, { x: 30, y: 75 }, { x: 15, y: 80 } // ソファ周辺
    ],
    working: [
        { x: 10, y: 20 }, { x: 40, y: 20 }, { x: 70, y: 20 }, // デスク
        { x: 15, y: 30 }, { x: 45, y: 30 }, { x: 75, y: 30 }
    ],
    thinking: [
        { x: 50, y: 50 }, { x: 40, y: 50 }, { x: 60, y: 50 } // 中央エリア
    ]
};

function updateClock() {
    const now = new Date();
    CLOCK_EL.innerText = now.toTimeString().split(' ')[0];
    UPTIME_EL.innerText = `UPTIME: ${Math.floor((Date.now() - startTime) / 1000)}s`;
}

async function fetchAgents() {
    try {
        // 本番環境では /api/agents から取得（開発時はモック検討）
        const response = await fetch('/api/agents');
        const data = await response.json();
        if (data.agents) {
            renderAgents(data.agents);
        }
    } catch (e) {
        console.error("Fetch error:", e);
    }
}

function renderAgents(agents) {
    AGENT_COUNT_EL.innerText = `AGENTS: ${agents.length}`;

    agents.forEach((agent, index) => {
        let el = document.getElementById(`agent-${agent.name}`);
        if (!el) {
            el = createAgentElement(agent);
            FLOOR_EL.appendChild(el);
        }

        // 位置の決定
        const pos = getTargetPosition(agent, index);
        el.style.left = `${pos.x}%`;
        el.style.top = `${pos.y}%`;

        // 吹き出しの更新
        const bubble = el.querySelector('.bubble');
        if (agent.thought && agent.status !== 'idle') {
            bubble.innerText = agent.thought;
            bubble.style.display = 'block';
        } else {
            bubble.style.display = 'none';
        }

        // ログの更新
        if (agent.thought && agentsData[agent.name]?.thought !== agent.thought) {
            addLog(agent.name, agent.thought);
        }

        agentsData[agent.name] = agent;
    });
}

function createAgentElement(agent) {
    const div = document.createElement('div');
    div.id = `agent-${agent.name}`;
    div.className = 'agent';

    const config = AGENT_CONFIG[agent.role.toLowerCase()] || AGENT_CONFIG.default;

    div.innerHTML = `
        <div class="bubble" style="display:none"></div>
        <div class="agent-sprite" style="background-color: ${config.color}">
            ${config.icon}
        </div>
        <div class="agent-name-tag">${agent.name.toUpperCase()}</div>
    `;
    return div;
}

function getTargetPosition(agent, index) {
    const status = agent.status || 'idle';
    const locs = LOCATIONS[status] || LOCATIONS.idle;
    // 重ならないように index でずらす
    const base = locs[index % locs.length];
    return {
        x: base.x + (Math.random() * 5 - 2.5),
        y: base.y + (Math.random() * 5 - 2.5)
    };
}

function addLog(name, thought) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="agent-name">[${name.toUpperCase()}]</span>: ${thought}`;
    LOG_CONTENT_EL.prepend(entry);

    // ログが多すぎたら削除
    if (LOG_CONTENT_EL.childNodes.length > 50) {
        LOG_CONTENT_EL.removeChild(LOG_CONTENT_EL.lastChild);
    }
}

setInterval(updateClock, 1000);
setInterval(fetchAgents, 3000);
fetchAgents();

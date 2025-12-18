// Language State
let currentLang = localStorage.getItem('whale_lang') || 'en';

const TRANSLATIONS = {
    en: {
        ai_title: "AI Market Insight",
        fg_title: "BTC Fear Index",
        fg_footer: "Macro Market Sentiment",
        timeline_title: "📡 7-Day Large Transfers",
        stat_volume: "Total Volume (7d)",
        stat_whales: "Active Whales",
        stat_top_whale: "Top Whale (7d)",
        stat_stable_flow: "Stablecoin Net Flow (7d)",
        stat_token_flow: "Token Net Flow (7d)",
        eth_sentiment: "ETH Sentiment",
        sol_sentiment: "SOL Sentiment",
        eth_risk_desc: "Institutional / Market Risk",
        sol_risk_desc: "Retail / Speculative Heat",
        flow_in_sell: "Inflow (Sell/Bear)",
        flow_in_buy: "Inflow (Buy Power)",
        flow_out_hodl: "Outflow (HODL)",
        flow_out_cash: "Outflow (Cash Out)",
        flow_transfer: "Transfer",
        sentiment_label: {
            "-2": "Strong Bearish",
            "-1": "Bearish",
            "0": "Neutral",
            "1": "Bullish",
            "2": "Strong Bullish"
        },
        fg_states: {
            "Extreme Fear": "Extreme Fear",
            "Fear": "Fear",
            "Neutral": "Neutral",
            "Greed": "Greed",
            "Extreme Greed": "Extreme Greed"
        },
        lbl_bullish: "Bullish",
        lbl_bearish: "Bearish",
        updated_at: "Updated at"
    },
    zh: {
        ai_title: "AI 市场洞察",
        fg_title: "BTC 恐慌指数",
        fg_footer: "宏观市场情绪",
        timeline_title: "📡 7日内大额转账",
        stat_volume: "总交易额 (7天)",
        stat_whales: "活跃巨鲸",
        stat_top_whale: "最大巨鲸 (7天)",
        stat_stable_flow: "稳定币净流向 (7天)",
        stat_token_flow: "代币净流向 (7天)",
        eth_sentiment: "ETH 情绪指数",
        sol_sentiment: "SOL 情绪指数",
        eth_risk_desc: "机构风向 / 市场风险",
        sol_risk_desc: "散户热度 / 投机情绪",
        flow_in_sell: "流入 (抛压/利空)",
        flow_in_buy: "流入 (买盘/利多)",
        flow_out_hodl: "流出 (囤币/利多)",
        flow_out_cash: "流出 (套现/利空)",
        flow_transfer: "转账",
        sentiment_label: {
            "-2": "强烈看空",
            "-1": "看空",
            "0": "中性",
            "1": "看多",
            "2": "强烈看多"
        },
        fg_states: {
            "Extreme Fear": "极度恐慌",
            "Fear": "恐慌",
            "Neutral": "中性",
            "Greed": "贪婪",
            "Extreme Greed": "极度贪婪"
        },
        lbl_bullish: "利多",
        lbl_bearish: "利空"
    }
};

// Ensure valid language
if (!['en', 'zh'].includes(currentLang)) {
    currentLang = 'en';
    localStorage.setItem('whale_lang', 'en');
}

async function loadData() {
    try {
        const res = await fetch('data/whale_analysis.json');
        const data = await res.json();
        renderDashboard(data);
    } catch (error) {
        console.error("Error loading data:", error);
        document.getElementById('ai-summary').innerHTML = `<div style="color:red">Error loading data: ${error.message}</div>`;
    }
}

function renderDashboard(data) {
    updateStaticText();

    // 1. Render AI Summary
    renderSummary(data.ai_summary, data.updated_at);

    // 2. Render Fear & Greed Index
    if (data.fear_greed) {
        renderFearGreed(data.fear_greed);
    }

    // 3. Render Gauges
    renderGauge('eth', data.eth.stats.sentiment_score);
    renderGauge('sol', data.sol.stats.sentiment_score);

    // 4. Render Stats & Timelines
    renderChainColumn('eth', data.eth);
    renderChainColumn('sol', data.sol);
}

function renderSummary(summaryData, updatedAt) {
    const container = document.getElementById('ai-summary');
    const text = summaryData[currentLang] || summaryData['en'] || "Summary unavailable.";

    let timeStr = "";
    if (updatedAt) {
        const date = new Date(updatedAt);
        // Format: YYYY-MM-DD HH:MM
        timeStr = `<div style="margin-top: 10px; font-size: 0.8rem; color: var(--text-secondary); text-align: right;">
            ${TRANSLATIONS[currentLang].updated_at || "Updated at"}: ${date.toLocaleString()}
        </div>`;
    }

    container.innerHTML = text.replace(/\n/g, '<br>') + timeStr;
}

function renderFearGreed(fgData) {
    const valEl = document.getElementById('fg-value');
    const labelEl = document.getElementById('fg-label');
    const barEl = document.getElementById('fg-bar-fill');

    valEl.innerText = fgData.value;

    // Translate state
    const state = fgData.value_classification;
    const translatedState = TRANSLATIONS[currentLang].fg_states[state] || state;
    labelEl.innerText = translatedState;

    // Update bar width
    if (barEl) {
        barEl.style.width = `${fgData.value}%`;
    }

    // Color coding
    let color = '#ffd700'; // Neutral
    if (fgData.value >= 75) color = '#00ff00'; // Extreme Greed
    else if (fgData.value >= 55) color = '#90ee90'; // Greed
    else if (fgData.value <= 25) color = '#ff0000'; // Extreme Fear
    else if (fgData.value <= 45) color = '#ff6b6b'; // Fear

    // Apply color to value and bar
    valEl.style.color = color;
    // labelEl.style.color = color; // Keep label neutral color for consistency with other gauges
    if (barEl) {
        barEl.style.background = color;
    }
}

function renderGauge(chain, score) {
    // Score: -2 to +2
    // Map to percentage: -2=0%, 0=50%, +2=100%
    const percentage = ((score + 2) / 4) * 100;

    document.getElementById(`${chain}-sentiment-val`).innerText = score > 0 ? `+${score}` : score;
    document.getElementById(`${chain}-gauge-fill`).style.width = `${Math.max(0, Math.min(100, percentage))}%`;

    // Label
    const t = TRANSLATIONS[currentLang].sentiment_label;
    let label = t["0"];
    if (score <= -1.5) label = t["-2"];
    else if (score <= -0.5) label = t["-1"];
    else if (score >= 1.5) label = t["2"];
    else if (score >= 0.5) label = t["1"];

    document.getElementById(`${chain}-sentiment-label`).innerText = label;
}

function renderChainColumn(chain, data) {
    // Stats
    document.getElementById(`${chain}-volume`).innerText = formatMoney(data.stats.total_volume);
    document.getElementById(`${chain}-whales`).innerText = data.stats.whale_count;

    // Top Whale Stat
    if (data.stats.top_whale) {
        const tw = data.stats.top_whale;
        document.getElementById(`${chain}-top-whale`).innerHTML = `
            <div style="color:var(--accent-${chain})">${tw.label}</div>
            <div style="color:var(--text-secondary); font-size:0.75em">${formatMoney(tw.volume)}</div>
        `;
    }

    const stableFlow = data.stats.stablecoin_net_flow;
    const tokenFlow = data.stats.token_net_flow;
    const t = TRANSLATIONS[currentLang];

    // Stablecoin Logic: >0 Bullish (Inflow), <0 Bearish (Outflow)
    const stableEl = document.getElementById(`${chain}-stable-flow`);
    let stableLabel = "";
    if (stableFlow > 0) stableLabel = ` (${t.lbl_bullish})`;
    else if (stableFlow < 0) stableLabel = ` (${t.lbl_bearish})`;

    stableEl.innerText = formatMoney(stableFlow) + stableLabel;
    stableEl.className = `stat-value ${stableFlow >= 0 ? 'text-green' : 'text-red'}`;

    // Token Logic: >0 Bearish (Selling), <0 Bullish (Buying/Holding)
    const tokenEl = document.getElementById(`${chain}-token-flow`);
    let tokenLabel = "";
    if (tokenFlow > 0) tokenLabel = ` (${t.lbl_bearish})`; // Positive = Inflow to Exchange = Sell
    else if (tokenFlow < 0) tokenLabel = ` (${t.lbl_bullish})`; // Negative = Outflow from Exchange = Buy

    tokenEl.innerText = formatMoney(tokenFlow) + tokenLabel;
    // Color: Green if Bullish (Negative Flow), Red if Bearish (Positive Flow)
    tokenEl.className = `stat-value ${tokenFlow <= 0 ? 'text-green' : 'text-red'}`;

    // Timeline
    const list = document.getElementById(`${chain}-timeline`);
    list.innerHTML = '';

    data.top_txs.forEach(tx => {
        const item = document.createElement('div');
        item.className = 'timeline-item';

        let flowClass = 'sentiment-neutral';
        let flowText = t.flow_transfer;

        // Logic: 
        // BULLISH_INFLOW / BULLISH_OUTFLOW -> Green (Bullish)
        // BEARISH_INFLOW / BEARISH_OUTFLOW -> Red (Bearish)

        if (tx.signal.includes('BULLISH')) {
            flowClass = 'sentiment-bullish'; // Green
            if (tx.signal.includes('INFLOW')) flowText = t.flow_in_buy; // Stablecoin In
            else flowText = t.flow_out_hodl; // Token Out
        } else if (tx.signal.includes('BEARISH')) {
            flowClass = 'sentiment-bearish'; // Red
            if (tx.signal.includes('INFLOW')) flowText = t.flow_in_sell; // Token In
            else flowText = t.flow_out_cash; // Stablecoin Out
        } else if (tx.pattern === 'INTERNAL_LOOP') {
            flowText = "Internal Loop";
        }

        item.innerHTML = `
            <div class="time">${formatTime(tx.timestamp)}</div>
            <div class="token">${tx.symbol}</div>
            <div class="amount">
                ${formatMoney(tx.amount_usd)}
            </div>
            <div class="flow">
                <span class="flow-tag ${flowClass}">${flowText}</span>
            </div>
        `;
        list.appendChild(item);
    });
}

function updateStaticText() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (TRANSLATIONS[currentLang][key]) {
            el.innerText = TRANSLATIONS[currentLang][key];
        }
    });
    document.getElementById('lang-toggle').innerText = currentLang === 'en' ? 'EN / 中文' : 'English / 中文';
}

function toggleLanguage() {
    currentLang = currentLang === 'en' ? 'zh' : 'en';
    localStorage.setItem('whale_lang', currentLang);
    loadData(); // Re-render
}

function formatMoney(amount) {
    if (Math.abs(amount) >= 1000000) {
        return `$${(amount / 1000000).toFixed(1)}M`;
    }
    return `$${(amount / 1000).toFixed(0)}k`;
}

function formatTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Event Listeners
document.getElementById('lang-toggle').addEventListener('click', toggleLanguage);

// Initial Load
loadData();

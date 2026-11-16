document.addEventListener("DOMContentLoaded", () => {
    // Navigation
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanes = document.querySelectorAll(".tab-pane");
    const pageTitle = document.getElementById("page-title");

    navItems.forEach(item => {
        item.addEventListener("click", () => {
            const targetTab = item.getAttribute("data-tab");
            navItems.forEach(i => i.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));

            item.classList.add("active");
            document.getElementById(`pane-${targetTab}`).classList.add("active");
            pageTitle.textContent = item.textContent.trim();

            if (targetTab === "keys") loadKeys();
            if (targetTab === "vectors") loadVectors();
        });
    });

    // Refresh button
    document.getElementById("refresh-btn").addEventListener("click", () => {
        loadStats();
        loadKeys();
        loadVectors();
    });

    // Stats fetching
    async function loadStats() {
        try {
            const res = await fetch("/api/stats");
            if (!res.ok) throw new Error("Stats unavailable");
            const data = await res.json();

            document.getElementById("metric-ops").textContent = data.ops_per_second;
            document.getElementById("metric-keys").textContent = data.dbsize;
            document.getElementById("metric-vectors").textContent = data.total_vectors;
            document.getElementById("metric-vector-indexes").textContent = `${data.vector_indexes} index(es)`;
            document.getElementById("metric-commands").textContent = data.total_commands.toLocaleString();

            document.getElementById("info-uptime").textContent = `${data.uptime}s`;
            document.getElementById("info-clients").textContent = data.connected_clients;
            
            const totalHits = data.keyspace_hits + data.keyspace_misses;
            const hitRate = totalHits > 0 ? ((data.keyspace_hits / totalHits) * 100).toFixed(1) + "%" : "100%";
            document.getElementById("info-hitrate").textContent = hitRate;

            document.getElementById("server-status").textContent = "ONLINE";
        } catch (err) {
            document.getElementById("server-status").textContent = "OFFLINE";
        }
    }

    // Keys fetching
    async function loadKeys() {
        try {
            const res = await fetch("/api/keys");
            const data = await res.json();
            const tbody = document.getElementById("keys-table-body");
            tbody.innerHTML = "";

            if (!data.keys || data.keys.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No keys found in database. Seed some or run SET in console!</td></tr>`;
                return;
            }

            data.keys.forEach(k => {
                const tr = document.createElement("tr");
                const ttlDisplay = k.ttl === -1 ? "None (Persistent)" : `${k.ttl}s`;
                tr.innerHTML = `
                    <td><strong>${escapeHtml(k.key)}</strong></td>
                    <td><span class="key-badge badge-${k.type}">${k.type.toUpperCase()}</span></td>
                    <td>${ttlDisplay}</td>
                    <td><code>${escapeHtml(k.preview)}</code></td>
                    <td>
                        <button class="btn btn-secondary btn-del-key" style="padding: 2px 8px; font-size: 0.75rem;" data-key="${escapeHtml(k.key)}">DEL</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            // Bind DEL buttons
            document.querySelectorAll(".btn-del-key").forEach(b => {
                b.addEventListener("click", async (e) => {
                    const key = e.target.getAttribute("data-key");
                    await executeCommand(`DEL ${key}`);
                    loadKeys();
                    loadStats();
                });
            });

        } catch (err) {
            console.error("Failed to load keys", err);
        }
    }

    // Filter Keys
    document.getElementById("btn-search-keys").addEventListener("click", () => {
        const pattern = document.getElementById("key-search-input").value.trim() || "*";
        executeCommand(`KEYS ${pattern}`).then(res => {
            loadKeys();
        });
    });

    // Vectors
    async function loadVectors() {
        try {
            const res = await fetch("/api/vectors");
            const data = await res.json();
            if (data.indexes && data.indexes.length > 0) {
                document.getElementById("vsearch-index").value = data.indexes[0].name;
            }
        } catch (err) {
            console.error(err);
        }
    }

    // Run Vector Search
    document.getElementById("btn-run-vsearch").addEventListener("click", async () => {
        const indexName = document.getElementById("vsearch-index").value.trim();
        const vectorRaw = document.getElementById("vsearch-vector").value.trim();
        const metric = document.getElementById("vsearch-metric").value;
        const topK = document.getElementById("vsearch-topk").value || 5;

        const cmd = `VSEARCH ${indexName} ${vectorRaw} ${topK} ${metric}`;
        const container = document.getElementById("vector-results-list");
        container.innerHTML = `<div class="empty-state">Searching...</div>`;

        try {
            const res = await fetch("/api/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: cmd })
            });
            const data = await res.json();
            
            // Format output
            container.innerHTML = "";
            const rawOut = data.output;
            
            if (!rawOut || rawOut.includes("(empty array)") || rawOut.trim() === "Array response:") {
                container.innerHTML = `<div class="empty-state">No matching vectors found in index '${indexName}'. Did you seed vectors first?</div>`;
                return;
            }

            container.innerHTML = `
                <div class="vector-result-card">
                    <div class="vector-result-header">
                        <strong>Raw Results for: <code>${escapeHtml(cmd)}</code></strong>
                    </div>
                    <pre style="font-family: var(--font-mono); font-size: 0.85rem; color: #a7f3d0; margin-top: 0.5rem;">${escapeHtml(rawOut)}</pre>
                </div>
            `;
            loadStats();
        } catch (err) {
            container.innerHTML = `<div class="empty-state" style="color: var(--accent-red)">Error executing vector search: ${err.message}</div>`;
        }
    });

    // Terminal
    const termInput = document.getElementById("terminal-input");
    const termOutput = document.getElementById("terminal-output");
    const cmdHistory = [];
    let historyIdx = -1;

    async function submitTerminal() {
        const cmd = termInput.value.trim();
        if (!cmd) return;

        cmdHistory.push(cmd);
        historyIdx = cmdHistory.length;
        termInput.value = "";

        appendTerminalLine(`flashkv> ${cmd}`, "terminal-cmd");

        const res = await executeCommand(cmd);
        if (res.error) {
            appendTerminalLine(`(error) ${res.error}`, "terminal-resp error");
        } else {
            appendTerminalLine(res.output, "terminal-resp");
        }

        loadStats();
    }

    document.getElementById("btn-term-send").addEventListener("click", submitTerminal);
    termInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            submitTerminal();
        } else if (e.key === "ArrowUp") {
            if (historyIdx > 0) {
                historyIdx--;
                termInput.value = cmdHistory[historyIdx];
            }
        } else if (e.key === "ArrowDown") {
            if (historyIdx < cmdHistory.length - 1) {
                historyIdx++;
                termInput.value = cmdHistory[historyIdx];
            } else {
                historyIdx = cmdHistory.length;
                termInput.value = "";
            }
        }
    });

    function appendTerminalLine(text, className) {
        const div = document.createElement("div");
        div.className = `terminal-line ${className}`;
        div.textContent = text;
        termOutput.appendChild(div);
        termOutput.scrollTop = termOutput.scrollHeight;
    }

    async function executeCommand(cmd) {
        try {
            const res = await fetch("/api/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: cmd })
            });
            return await res.json();
        } catch (err) {
            return { error: err.message };
        }
    }

    // Quick Play: Seed Data
    document.getElementById("btn-seed-data").addEventListener("click", async () => {
        const seeds = [
            "SET user:101:name 'Alice Johnson'",
            "SET user:101:role 'Lead Architect'",
            "SET system:status 'nominal' EX 300",
            "LPUSH task_queue 'build_docker' 'run_tests' 'deploy_prod'",
            "HSET cache:config timeout 30 max_conns 1000 keep_alive true",
            "SADD active_regions 'us-east' 'eu-central' 'ap-southeast'"
        ];
        for (const s of seeds) {
            await executeCommand(s);
        }
        alert("Sample Key-Values seeded successfully!");
        loadStats();
        loadKeys();
    });

    // Quick Play: Seed Vectors
    document.getElementById("btn-seed-vectors").addEventListener("click", async () => {
        const vectors = [
            `VADD documents doc1 0.23,0.85,0.11,0.52 {"title":"Introduction to Distributed Systems","category":"tech"}`,
            `VADD documents doc2 0.25,0.89,0.14,0.50 {"title":"Deep Learning with Transformer Architecture","category":"ai"}`,
            `VADD documents doc3 0.89,0.12,0.76,0.34 {"title":"Delicious Pasta Carbonara Recipe","category":"cooking"}`,
            `VADD documents doc4 0.92,0.10,0.80,0.28 {"title":"Traditional Italian Pizza Making","category":"cooking"}`,
            `VADD documents doc5 0.30,0.78,0.20,0.61 {"title":"Building Custom Redis in Python","category":"engineering"}`
        ];
        for (const v of vectors) {
            await executeCommand(v);
        }
        alert("5 AI Vector Embeddings seeded in index 'documents'!");
        loadStats();
        loadVectors();
    });

    function escapeHtml(str) {
        if (!str) return "";
        return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    // Auto refresh stats every 2 seconds
    loadStats();
    setInterval(loadStats, 2000);
});

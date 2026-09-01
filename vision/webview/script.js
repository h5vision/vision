// DOM이 완전히 로드된 후 이벤트를 안전하게 부착합니다.
document.addEventListener("DOMContentLoaded", () => {
    
    // 서버 재연결 버튼
    const reconnectBtn = document.getElementById("reconnect-btn");
    reconnectBtn.addEventListener("click", () => {
        document.getElementById("backend-status").textContent = '🟡 Server Reconnecting...';
        document.getElementById("endpoint").textContent = '';
        vscode.postMessage({ command: "checkBackend" });
    });

    // endpoint 변경 버튼
    const endpoint = document.getElementById("endpoint");
    const endpointEditInput = document.getElementById('endpoint-edit-input');
    const changeEndpoint = document.getElementById('change-endpoint');
    const cancelEndpoint = document.getElementById('cancel-endpoint');
    endpoint.addEventListener("click", ()=>{
        endpoint.classList.toggle('hidden');
        endpointEditInput.classList.toggle('hidden');
        endpointEditInput.focus();
        changeEndpoint.classList.toggle('hidden');
        cancelEndpoint.classList.toggle('hidden');
        endpointEditInput.value = endpoint.textContent;
    });
    endpointEditInput.addEventListener('keydown', (e)=>{
        if (e.key === 'Enter') {changeEndpoint.click();}
    });
    changeEndpoint.addEventListener("click", ()=>{
        if (endpoint.textContent === endpointEditInput.value) {cancelEndpoint.click(); return;}
        else if (endpointEditInput.value.trim() === "") {
            cancelEndpoint.click();
            return;
        };
        endpoint.textContent = endpointEditInput.value;
        endpoint.click();
        document.getElementById("backend-status").textContent = '🟡 Server Reconnecting...';
        vscode.postMessage({command:"updateEndpoint", data: endpointEditInput.value});
    });
    cancelEndpoint.addEventListener("click", ()=>{
        endpoint.click();
    });

    // 스트리밍 토글 버튼 이벤트
    const toggleStreamingBtn = document.getElementById("toggle-streaming-btn");
    toggleStreamingBtn.addEventListener("click", () => {
        if (toggleStreamingBtn.classList.contains('ON')) {
            toggleStreamingBtn.classList.remove('ON');
            toggleStreamingBtn.textContent = "OFF";
            vscode.postMessage({ command: "setStreaming", data: false });
        } else {
            toggleStreamingBtn.classList.add('ON');
            toggleStreamingBtn.textContent = "ON";
            vscode.postMessage({ command: "setStreaming", data: true });
        }
    });

    // 현재 프로젝트 정보 재연결 버튼
    const reconnectProjectInfoBtn = document.getElementById("reconnect-project-info-btn");
    reconnectProjectInfoBtn.addEventListener("click", () => {
        vscode.postMessage({ command: "getProjectInfo" });
        vscode.postMessage({ command: "getProjectGitInfo" });
    });

    // 프로젝트 브리핑 열기
    const prjBriefBtn = document.getElementById("project-brief-btn");
    prjBriefBtn.addEventListener("click", () => {
        vscode.postMessage({ command: "getProjectBrief" });
    });

    // 의존성 그래프 열기 버튼 이벤트
    const openGraphBtn = document.getElementById("open-graph-btn");
    openGraphBtn.addEventListener("click", () => {
        vscode.postMessage({ command: "showDependencyGraph" });
    });
    openGraphBtn.style.display = 'none';

    // Project List 새로고침
    const refreshProjectBtn = document.getElementById("refresh-projects-btn");
    refreshProjectBtn.addEventListener("click", () => {
        const prjList = document.getElementById('project-list-content');
        prjList.innerHTML = `<div style="padding: 4px 0; opacity: 0.8;">• 프로젝트 목록을 불러오는 중...</div>`;
        setTimeout(()=>vscode.postMessage({ command: "getProjectList" }), 1000);
    });

    // 💡 [추가 완료] 가이드북 켜기/끄기 토글 버튼 이벤트
    const toggleGuideBtn = document.getElementById("toggle-guide-btn");
    toggleGuideBtn.addEventListener("click", () => {
        vscode.postMessage({ command: "toggleGuide" });
    });

    // // 프로젝트 브리핑 생성 by Copilot
    // const copilotBriefGenBtn = document.getElementById("copilot-gen-brief-btn");
    // copilotBriefGenBtn.addEventListener("click", () => {
    //     vscode.postMessage({ command: "generateBriefByCopilot" });
    // });

    // const genRAGTBtn = document.getElementById("gen-RAGTEST-btn");
    // genRAGTBtn.addEventListener("click", () => {
    //     const testN = document.getElementById('testN').value;
    //     vscode.postMessage({ command: "generateRAGTEST", data: Number(testN)});
    // });

    // const removeRAGTBtn = document.getElementById("remove-RAGTEST-btn");
    // removeRAGTBtn.addEventListener("click", () => {
    //     vscode.postMessage({ command: "removeRAGTEST" });
    // });

    // Chat History.db 열기 버튼 이벤트
    const openDBExternalBtn = document.getElementById("open-db-external-btn");
    openDBExternalBtn.addEventListener("click", () => {
        vscode.postMessage({ command: "openDBExternal" });
    });

});

const vscode = acquireVsCodeApi();

function updateBackendStatus(status) {

    const el = document.getElementById("backend-status");
    const el2 = document.getElementById("endpoint");
    const el3 = document.getElementById("server-status-icon");
    el2.textContent = status.endpoint;

    if (status.connected) {
        el.textContent = "🟢 " + status.message + ` [ ${status.latency} ms ]`;
        el3.classList.replace('codicon-vm', 'codicon-vm-active');
    } else {
        el.textContent = "🔴 " + status.message;
        el3.classList.replace('codicon-vm-active', 'codicon-vm');
    }

}

function renderProjectList(projects) {
    const container = document.getElementById("project-list-content");
    if (!container) {return;}

    if (!projects || projects.length === 0) {
        container.innerHTML = '<div>• 등록된 프로젝트 목록이 없습니다.</div>';
        return;
    }

    container.innerHTML = '';
    projects.sort((a, b) => a.id - b.id);
    projects.forEach(proj => {
        const projectItem = document.createElement('div');
        projectItem.className = 'project-item';

        const titleEl = document.createElement('div');
        titleEl.className = 'project-title';

        const iconEl = document.createElement('i');
        iconEl.id = `icon-${proj.id}`;
        iconEl.className = 'codicon codicon-chevron-right';

        const textEl = document.createElement('span');
        textEl.textContent = `${proj.name}`;

        const locationEl = document.createElement('span');
        locationEl.className = 'badge';
        if (proj.location === 'Local') {
            locationEl.style.color = '#32b1ff';
        } else if (proj.location === 'DB') {
            locationEl.style.color = 'var(--vscode-terminal-ansiGreen';
        }
        locationEl.textContent = `${proj.location}`;

        titleEl.appendChild(iconEl);
        titleEl.appendChild(textEl);
        titleEl.appendChild(locationEl);

        const commitListEl = document.createElement('div');
        commitListEl.classList.add('commit-list', 'hidden');
        commitListEl.id = `commits-${proj.id}`;

        if (proj.commits && proj.commits.length > 0 && !!proj.commits[0][0]) {
            proj.commits.forEach(([SHA, message]) => {
                const commitItem = document.createElement('div');
                commitItem.innerHTML = `<i class="codicon codicon-git-commit"></i>${SHA.slice(0,7)} ─ ${message}`;
                commitItem.className = 'commit-item badge ellipsis';
                commitItem.addEventListener('click', () => {
                    vscode.postMessage({ 
                        command: "updateCommitId", 
                        data: { 
                            project_id: proj.id, 
                            name: proj.name || 'unknown',
                            commit: SHA, 
                            path: proj.location,
                            branch: '임시'
                        } 
                    });
                });
                commitListEl.appendChild(commitItem);
            });
        } else {
            const noCommit = document.createElement('div');
            noCommit.style.opacity = '0.5';
            noCommit.textContent = '• 커밋 내역 없음';
            commitListEl.appendChild(noCommit);
        }

        titleEl.addEventListener('click', () => {
            const isHidden = commitListEl.classList.contains('hidden');
            if (isHidden) {
                commitListEl.classList.remove('hidden');
                iconEl.classList.replace('codicon-chevron-right', 'codicon-chevron-down');
            } else {
                commitListEl.classList.add('hidden');
                iconEl.classList.replace('codicon-chevron-down', 'codicon-chevron-right');
            }
        });

        projectItem.appendChild(titleEl);
        projectItem.appendChild(commitListEl);
        container.appendChild(projectItem);
    });
}

function updateDependencyGraphStatus(progress) {
    const graphStatus = document.getElementById('graph-status');    
    const gIcon = document.getElementById('graph-status-icon');
    const progressFill = document.getElementById('graph-progress-fill');

    graphStatus.textContent = progress.message || '';
    
    switch (progress.status) {
        case 'idle':
            return;
        case 'building [Node]':
            graphStatus.textContent = '프로젝트 구조 분석 중 [Node]';
            break;
        case 'building [Edge]':
            graphStatus.textContent = '프로젝트 구조 분석 중 [Edge]';
            break;
        case 'ready':
            gIcon.className = 'codicon codicon-verified';
            break;
        case 'error':
            gIcon.className = 'codicon codicon-error';
            return;
        default:
            gIcon.className = 'codicon codicon-unverified';
            graphStatus.textContent = '알 수 없는 상태';
            return;
    }
    if (progress.status === 'building [Node]' && progress.total > 0) {
        const percent = Math.round((progress.current / progress.total) * 20);
        progressFill.style.width = `${percent}%`;
        graphStatus.textContent += ` (${progress.current} / ${progress.total})`;
    }
    if (progress.status === 'building [Edge]' && progress.total > 0) {
        const percent = 20 + Math.round((progress.current / progress.total) * 80);
        progressFill.style.width = `${percent}%`;
        graphStatus.textContent += ` (${progress.current} / ${progress.total})`;
    }

    if (progress.status === 'ready') {
        progressFill.style.width = '100%';
        progressFill.style.backgroundColor = 'var(--vscode-terminal-ansiGreen)';
        document.getElementById('open-graph-btn').style.display = 'block';
    }
    
}

vscode.postMessage({ command: "getProjectInfo" });
vscode.postMessage({ command: "getGuideStatus" });
vscode.postMessage({ command: "getDependencyGraphStatus" });
vscode.postMessage({ command: "getStreamingStatus" });

setTimeout(() => {
    vscode.postMessage({ command: "checkBackend" });
}, 100);

setTimeout(() => {
    vscode.postMessage({ command: "getProjectGitInfo" });
    vscode.postMessage({ command: "getProjectList" });
}, 1000);


setInterval(() => {
    vscode.postMessage({ command: "checkBackend" });
}, 30 * 1000);


window.addEventListener("message", event => {

    const message = event.data;

    switch (message.command) {
        case "streamingStatus": {
            const toggleStreamingBtn = document.getElementById("toggle-streaming-btn");
            if (message.data) {
                if (!toggleStreamingBtn.classList.contains("ON")) {
                    toggleStreamingBtn.classList.add("ON");
                }
                toggleStreamingBtn.textContent = "ON";
            } else {
                if (toggleStreamingBtn.classList.contains("ON")) {
                    toggleStreamingBtn.classList.remove("ON");
                }
                toggleStreamingBtn.textContent = "OFF";
            }
            break;
        }
        case "backendStatus": {
            updateBackendStatus(message.data);
            break;
        }

        case "showProjectInfo": {
            const el = document.getElementById('current-project-name');
            const data = message.data;
            el.textContent = data.name.toUpperCase();
            break;
        }

        case "showProjectGitInfo": {
            const elgit = document.getElementById('current-git-info');
            elgit.textContent = "";
            const data = message.data;
            if (data.git) {
                elgit.textContent = data.repository.branch;
                elgit.innerHTML = `<i class="codicon codicon-git-branch"></i> ${data.repository.commit.slice(0,7)} &nbsp; <b><i class="codicon codicon-target"></i>${data.repository.branch}</b>`;
            } else {
                elgit.textContent = "❌ 정보없음";
            }
            break;
        }

        case "dependencyGraphStatus": {
            updateDependencyGraphStatus(message.data);
            break;
        }

        case "commitIdUpdated": {
            document.getElementById('ask-project-info').classList.remove('hidden');
            document.getElementById('ask-project-header').classList.remove('hidden');
            const data = message.data;
            document.getElementById('ask-project-name').textContent = data.name.toUpperCase();
            document.getElementById('ask-project-path').textContent = data.path;
            if (data.path === 'Local') {
                document.getElementById('ask-project-path').style.color = '#32b1ff';
            } else if (data.path === 'DB') {
                document.getElementById('ask-project-path').style.color = '#4CAF50';
            }
            document.getElementById('ask-git-info').innerHTML = `<i class="codicon codicon-git-commit"></i> ${data.commit.slice(0,7)} &nbsp; <b><i class="codicon codicon-target"></i>${data.branch}</b>`;
            break;
        }
        
        case "cardClick": {
            const targetElement = document.getElementById(message.data);
            if (targetElement) {
                targetElement.classList.add('flash-effect');
                setTimeout(() => {
                    targetElement.classList.remove('flash-effect');
                }, 1000);
            }
            break;
        }

        case "guideStatus": {
            const guideStatus = message.data;
            document.getElementById("GuideStatus").textContent = guideStatus ? "닫기" : "열기";
            break;
        }

        case "showProjectList": {
            renderProjectList(message.data);
            break;
        }
    }
});

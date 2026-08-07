// DOM이 완전히 로드된 후 이벤트를 안전하게 부착합니다.
document.addEventListener("DOMContentLoaded", () => {
    
    // 서버 재연결 버튼
    const reconnectBtn = document.getElementById("reconnect-btn");
    if (reconnectBtn) {
        reconnectBtn.addEventListener("click", () => {
            document.getElementById("backend-status").textContent = '🟡 Server Reconnecting...';
            document.getElementById("endpoint").textContent = '';
            vscode.postMessage({ command: "checkBackend" });
        });
    }

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
        if (endpoint.textContent === endpointEditInput.value) {cancelEndpoint.click(); return;};
        endpoint.textContent = endpointEditInput.value;
        endpoint.click();
        document.getElementById("backend-status").textContent = '🟡 Server Reconnecting...';
        vscode.postMessage({command:"updateEndpoint", data: endpointEditInput.value});
    });
    cancelEndpoint.addEventListener("click", ()=>{
        endpoint.click();
    });

    // 실패 파일 목록 토글
    const errorToggleBtn = document.getElementById("error-toggle-btn");
    const errorListContent = document.getElementById("errorListContent");
    if (errorToggleBtn && errorListContent) {
        errorToggleBtn.addEventListener("click", () => {
            if (errorListContent.style.display === 'none' || errorListContent.style.display === '') {
                errorListContent.style.display = 'block';
            } else {
                errorListContent.style.display = 'none';
            }
        });
    }

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

    // 프로젝트 브리핑 by Copilot
    const prjBriefBtn = document.getElementById("project-brief-btn");
    prjBriefBtn.addEventListener("click", () => {
        vscode.postMessage({ command: "generateProjectBrief" });
    });

    const genRAGTBtn = document.getElementById("gen-RAGTEST-btn");
    genRAGTBtn.addEventListener("click", () => {
        const testN = document.getElementById('testN').value;
        vscode.postMessage({ command: "generateRAGTEST", data: Number(testN)});
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

function updateModelsInfo(models) {
    const scrollContainer = document.getElementById("model-list-scroll");
    if (!scrollContainer) {return;}

    if (!models || models.length === 0) {
        scrollContainer.textContent = '• 등록된 모델이 없습니다.';
        return;
    }

    scrollContainer.textContent = models[0].model_name;
    scrollContainer.innerHTML = '';
    models.forEach(model => {
        const option = document.createElement('option');
        option.value = model.model_id;
        option.textContent = model.model_name;
        scrollContainer.appendChild(option);
    });
}

function renderProjectList(projects) {
    const container = document.getElementById("project-list-content");
    if (!container) {return;}

    if (!projects || projects.length === 0) {
        container.innerHTML = '<div style="padding: 4px 0; opacity: 0.8;">• 등록된 프로젝트 목록이 없습니다.</div>';
        return;
    }

    container.innerHTML = '';
    projects.sort((a, b) => a.id - b.id);
    projects.forEach(proj => {
        const projectItem = document.createElement('div');
        projectItem.className = 'project-item';
        projectItem.style.marginBottom = '8px';

        const titleEl = document.createElement('div');
        titleEl.className = 'project-title';
        titleEl.style.cursor = 'pointer';
        titleEl.style.display = 'flex';
        titleEl.style.alignItems = 'center';
        titleEl.style.fontWeight = '600';
        titleEl.style.padding = '4px 0';

        const iconEl = document.createElement('i');
        iconEl.id = `icon-${proj.id}`;
        iconEl.className = 'codicon codicon-chevron-right';
        iconEl.style.marginRight = '4px';

        const textEl = document.createElement('span');
        textEl.textContent = `${proj.name}`;

        const locationEl = document.createElement('span');
        locationEl.className = 'badge';
        locationEl.textContent = `${proj.location}`;

        titleEl.appendChild(iconEl);
        titleEl.appendChild(locationEl);
        titleEl.appendChild(textEl);

        const commitListEl = document.createElement('div');
        commitListEl.className = 'commit-list';
        commitListEl.id = `commits-${proj.id}`;
        commitListEl.style.display = 'none';
        commitListEl.style.paddingLeft = '2px';
        commitListEl.style.flexDirection = 'column';
        commitListEl.style.gap = '3px';
        commitListEl.style.marginTop = '0px';

        if (proj.commits && proj.commits.length > 0 && !!proj.commits[0]) {
            proj.commits.forEach(commit => {
                const commitItem = document.createElement('div');
                commitItem.innerHTML = `<i class="codicon codicon-git-commit"></i> ${commit}`;
                commitItem.className = 'commit-item badge ellipsis';
                commitListEl.appendChild(commitItem);
            });
        } else {
            const noCommit = document.createElement('div');
            noCommit.style.opacity = '0.5';
            noCommit.textContent = '• 커밋 내역 없음';
            commitListEl.appendChild(noCommit);
        }

        // 클릭 시 안전하게 토글 실행 (CSP 보안 정책 우회)
        titleEl.addEventListener('click', () => {
            const isHidden = commitListEl.style.display === 'none' || commitListEl.style.display === '';
            if (isHidden) {
                commitListEl.style.display = 'block';
                iconEl.classList.replace('codicon-chevron-right', 'codicon-chevron-down');
            } else {
                commitListEl.style.display = 'none';
                iconEl.classList.replace('codicon-chevron-down', 'codicon-chevron-right');
            }
        });

        projectItem.appendChild(titleEl);
        projectItem.appendChild(commitListEl);
        container.appendChild(projectItem);
    });
}

vscode.postMessage({ command: "checkBackend" });
vscode.postMessage({ command: "getModelsInfo" });
vscode.postMessage({ command: "getProjectInfo" });
vscode.postMessage({ command: "getProjectGitInfo" });
vscode.postMessage({ command: "getGuideStatus" });
vscode.postMessage({ command: "getProjectList" });


setInterval(() => {
    vscode.postMessage({ command: "checkBackend" });
    vscode.postMessage({ command: "getModelsInfo" });
}, 30 * 1000);


window.addEventListener("message", event => {

    const message = event.data;

    switch (message.command) {

        case "backendStatus": {
            updateBackendStatus(message.data);
            break;
        }
        case "showModelsInfo": {
            updateModelsInfo(message.data);
            break;
        }

        case "showProjectInfo": {
            const el = document.getElementById('current-project-name');
            const elPath = document.getElementById('current-project-path');
            const data = message.data;
            el.textContent = data.name.toUpperCase();
            elPath.textContent = data.path;
            break;
        }

        case "showProjectGitInfo": {
            const elgit = document.getElementById('current-git-info');
            const data = message.data;
            let git = '';
            if (data.git) {
                elgit.textContent = data.repository.branch;
                elgit.innerHTML = `<i class="codicon codicon-git-branch"></i>&nbsp; ${data.repository.commit.slice(0,7)} &nbsp; <b><i class="codicon codicon-target"></i> ${data.repository.branch}</b>`;
            } else {
                git = "❌ 정보없음";
                elgit.textContent = git;
            }
            
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


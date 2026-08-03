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
    if (endpoint) {
        endpoint.addEventListener("click", ()=>{
            endpoint.classList.toggle('hidden');
            endpointEditInput.classList.toggle('hidden');
            endpointEditInput.focus();
            changeEndpoint.classList.toggle('hidden');
            cancelEndpoint.classList.toggle('hidden');
            endpointEditInput.value = endpoint.textContent;
        });
    };
    if (endpointEditInput) {
        endpointEditInput.addEventListener('keydown', (e)=>{
            if (e.key === 'Enter') {changeEndpoint.click();}
        });
    }

    if (changeEndpoint) {
        changeEndpoint.addEventListener("click", ()=>{
            if (endpoint.textContent === endpointEditInput.value) {cancelEndpoint.click(); return;};
            endpoint.textContent = endpointEditInput.value;
            endpoint.click();
            document.getElementById("backend-status").textContent = '🟡 Server Reconnecting...';
            vscode.postMessage({command:"updateEndpoint", data: endpointEditInput.value});
        });
    };

    if (cancelEndpoint) {
        cancelEndpoint.addEventListener("click", ()=>{
            endpoint.click();
        });
    };


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

vscode.postMessage({ command: "checkBackend" });
vscode.postMessage({ command: "getProjectInfo" });
vscode.postMessage({ command: "getProjectGitInfo" });

setInterval(() => {vscode.postMessage({ command: "checkBackend" });}, 30 * 1000);


window.addEventListener("message", event => {

    const message = event.data;

    switch (message.command) {

        case "backendStatus": {
            updateBackendStatus(message.data);
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
            const el = document.getElementById('current-project-git');
            const data = message.data;
            let git = '';
            if (data.git) {git = "✅ 사용 중";} else {git = "❌ 정보없음";}
            el.textContent = git;
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
    }
});


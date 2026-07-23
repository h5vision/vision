const headers = document.querySelectorAll(".panel-header");

// DOM이 완전히 로드된 후 이벤트를 안전하게 부착합니다.
document.addEventListener("DOMContentLoaded", () => {
    
    // ① 서버 재연결 버튼
    const reconnectBtn = document.getElementById("reconnect-btn");
    if (reconnectBtn) {
        reconnectBtn.addEventListener("click", () => {
            vscode.postMessage({ command: "reconnectServer" });
        });
    }

    // ② 프로젝트 인덱싱 실행 버튼
    const indexingButton = document.getElementById("project-indexing-btn");
    if (indexingButton) {
        indexingButton.addEventListener("click", () => {
            vscode.postMessage({ command: "projectIndexing" });
        });
    }

    // ③ 실패 파일 목록 토글
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

    // ④ 질의응답 히스토리 토글 (기본 접혀있다가 클릭하면 펴짐)
    const historyHeader = document.getElementById("history-header");
    const historyContent = document.getElementById("history-content");
    const historyArrow = document.getElementById("history-arrow");
    if (historyHeader && historyContent) {
        historyHeader.addEventListener("click", () => {
            if (historyContent.style.display === 'none' || historyContent.style.display === '') {
                historyContent.style.display = 'block';
                if (historyArrow) {historyArrow.textContent = '▲';}
            } else {
                historyContent.style.display = 'none';
                if (historyArrow) {historyArrow.textContent = '▼';}
            }
        });
    }
});

const vscode = acquireVsCodeApi();

function updateBackendStatus(status) {

    const el = document.getElementById("backend-status");

    if (status.connected) {
        el.textContent = "🟢 " + status.message + ` [ ${status.latency} ms ]`;
    } else {
        el.textContent = "🔴 " + status.message;
    }

}

vscode.postMessage({ command: "checkBackend" });

setInterval(() => {vscode.postMessage({ command: "checkBackend" });}, 30 * 1000);


window.addEventListener("message", event => {

    const message = event.data;

    switch (message.command) {

        case "backendStatus":
            updateBackendStatus(message.data);
            break;

        case "displayProject":
            // 프로젝트 인덱싱 진행 후 sidebar에 출력하는 기능을 입력합니다. 
            break;
    }
});

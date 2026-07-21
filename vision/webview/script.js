const headers = document.querySelectorAll(".panel-header");

headers.forEach(header => {

    header.addEventListener("click", () => {

        header.classList.toggle("active");

        const content =
            header.nextElementSibling;

        content.classList.toggle("show");

    });

});

const vscode = acquireVsCodeApi();

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

function updateBackendStatus(status) {

    const el = document.getElementById("backend-status");

    if (status.connected) {
        el.textContent = "🟢 " + 'Server ' + status.message;
    } else {
        el.textContent = "🔴 " + 'Server ' + status.message;
    }

}

vscode.postMessage({ command: "checkBackend" });

setInterval(() => {vscode.postMessage({ command: "checkBackend" });}, 3 * 60 * 1000);


// project indexing 기능 
vscode.postMessage({commend:"initialProjectIndexing"});

const indexingButton = document.getElementById("project-indexing-btn");
indexingButton.addEventListener("click", () => {
    vscode.postMessage({command: "projectIndexing"});
});
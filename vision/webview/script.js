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

    }

});

function updateBackendStatus(status) {

    const el = document.getElementById("backend-status");

    if (status.connected) {
        el.textContent = "🟢 " + status.message;
    } else {
        el.textContent = "🔴 " + status.message;
    }

}

vscode.postMessage({ command: "checkBackendStatus" });

setInterval(() => {vscode.postMessage({ command: "checkBackendStatus" });}, 30000);
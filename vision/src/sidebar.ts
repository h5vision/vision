// import * as vscode from "vscode";
// import { getWebviewContent } from "./sidebarContents";

// export class SidebarProvider implements vscode.WebviewViewProvider {
//     private _view?: vscode.WebviewView;
//     public static readonly viewType = "VisionAssistant.sidebar";

//     constructor(
//         private readonly extensionUri: vscode.Uri
//     ){}

//     private async checkBackend() {

//         try {
//             const response = await fetch("http://localhost:8000/health");
//             this.sendMessage("backendStatus", {
//                 connected: response.ok
//             });
//         }
//         catch {
//             this.sendMessage("backendStatus", {
//                 connected: false
//             });
//         }
//     }
//     resolveWebviewView(
//         webviewView: vscode.WebviewView
//     ){
//         this._view = webviewView;

//         webviewView.webview.options = {
//             enableScripts: true,
//             localResourceRoots: [
//                 this.extensionUri
//             ]
//         };

//         webviewView.webview.html =
//             getWebviewContent(
//                 webviewView.webview,
//                 this.extensionUri
//             );
        
//         // JS -> Extension 메시지 수신
//         webviewView.webview.onDidReceiveMessage(async message => {

//             switch (message.command) {

//                 case "checkBackend":
//                     await this.checkBackend();
//                     break;

//             }

//         });
//     }
//     // Extension -> JS 메시지 전송
//     public sendMessage(command: string, data: any) {

//         this._view?.webview.postMessage({
//             command,
//             data
//         });

//     }

// }
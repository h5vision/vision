// 'vscode' 모듈에는 VS Code 확장 API가 포함되어 있습니다. 이 모듈을 가져오면 편집기와 상호 작용할 수 있습니다.
import * as vscode from 'vscode';
import * as path from 'path';  		// Node.js의 path 모듈을 가져옵니다. 파일 경로를 다루는 데 사용됩니다.
import * as fs from "fs";
import { SidebarProvider } from "./providers/sidebarProvider";	// SidebarProvider를 가져옵니다.
import { getHtmlContent } from "./providers/guideContents";		// guideBook.html 파일을 읽어오는 함수를 가져옵니다.
import { ChatHandler } from './chat/chatHandler';	// chatParticipant 등록을 위한 chatHandler를 가져옵니다. 
// vscode의 Explorer에서, 파일의 의존성과 sllm 답변 출처 파일의 파일명에 색을 입히는 provider를 가져옵니다. 
import { dependencyDecorationProvider } from "./providers/dependencyDecorationProvider";
import { HistoryService } from './services/historyService';

// 이 메서드는 확장 프로그램이 활성화될 때 호출됩니다. 확장 프로그램이 처음으로 명령을 실행할 때 활성화됩니다.
export async function activate(context: vscode.ExtensionContext) {

	// 진단 정보를 출력하거나 오류를 출력하려면 콘솔을 사용하세요. 이 코드 줄은 확장 프로그램이 활성화될 때 한 번만 실행됩니다.
	console.log('Congratulations, your extension "vision" is now active!');

	// 이 명령은 package.json 파일에 정의되어 있습니다. 명령의 구현을 registerCommand로 제공합니다. 
	// commandId 매개변수는 package.json의 command 필드와 일치해야 합니다.
	const disposable = vscode.commands.registerCommand('vision.helloWorld', () => {
		// 여기에 명령이 실행될 때마다 실행되는 코드를 작성하세요
		// 사용자의 메시지 상자에 'Hello World from vision!'을 표시합니다.
		vscode.window.showInformationMessage('Hello World from vision!');
	});
	context.subscriptions.push(disposable);	// 명령을 구독에 추가하여 확장 프로그램이 비활성화될 때 정리할 수 있도록 합니다.


	//// 확장 프로그램 실행 시 guideBook.html 파일을 웹뷰로 자동 실행
	// Test: F5를 눌러 확장 프로그램이 로드되는 순간, guideBook.html 내용을 웹뷰 창으로 자동 실행
	const guidepanel = vscode.window.createWebviewPanel(
		'visionGuide', 
		'Vision Guide', 
		vscode.ViewColumn.One, 
		{ 
			enableScripts: true,
			localResourceRoots: [
				vscode.Uri.file(path.join(context.extensionPath))
			]
		}
	);
	// 프로젝트 루트에 있는 진짜 guideBook.html 파일을 읽어서 웹뷰에 주입
	guidepanel.webview.html = getHtmlContent(context, guidepanel);
	////

	// SidebarProvider를 등록하여 웹뷰를 표시할 수 있도록 설정
	const provider = new SidebarProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            "VisionAssistant.sidebar",
            provider
        )
    );

	// guideBook.html<script>에서 Sidebar script.js로 명령 전달
	guidepanel.webview.onDidReceiveMessage((message) => {
		console.log(message.command);
		if (provider && provider.view) {
			return provider.view.webview.postMessage(message);
		}
	});
	
	// Extension을 실행할 때 vscode chat 창을 자동으로 열어줍니다. 
	await vscode.commands.executeCommand("workbench.action.chat.open");
	
	// vscode 내의 Storage에 history.db 파일을 만듭니다. 
	
	const storagePath = path.join(context.globalStorageUri.fsPath);
	try {
		if (!fs.existsSync(storagePath)) {
			fs.mkdirSync(storagePath,{recursive:true});
		}
		const dbPath = path.join(storagePath, 'history.db');
		const historyService = new HistoryService(dbPath);
		if (historyService) {
			console.log('history.db has been initialized');
		}

		// ChatParticipantProvider를 구독에 추가하여 확장 프로그램이 비활성화될 때 정리할 수 있도록 합니다.
		const chatHandler = new ChatHandler(historyService);
		vscode.chat.createChatParticipant("vision.chat", chatHandler.handle);
	} catch(err) {
		console.log(err);
	}


	// 현재 함수/변수에 대한 의존성을 vscode Explorer 창의 파일들에 색상으로 표시합니다. 
	const decorationProvider = new dependencyDecorationProvider();
	context.subscriptions.push(
		vscode.window.registerFileDecorationProvider(decorationProvider)
	);


	// 우클릭하여 파일에 대한 질문 / 블록 설정한 코드에 대한 질문을 vscode chat view에 주입
	const explainFileDisposable = vscode.commands.registerCommand('vision.explainFile', async () => {
        const activeEditor = vscode.window.activeTextEditor;
        
        if (!activeEditor) {
            vscode.window.showInformationMessage('열려 있는 에디터가 없습니다.');
            return;
        }

        const selection = activeEditor.selection;
        const selectedText = activeEditor.document.getText(selection);
        const fileName = path.basename(activeEditor.document.uri.fsPath);

        if (!selectedText || selectedText.trim().length === 0) {
            await vscode.commands.executeCommand('workbench.action.chat.open', {
				path: '',
            	query: `@vision ${fileName}에 대해 설명해줘.`,
				isPartialQuery: false
        	});
			return;
        }

        // VS Code 챗 창을 열면서 @vision chat view 입력창에 드래그한 코드 자동 입력
        await vscode.commands.executeCommand('workbench.action.chat.open', {
			path: '', 
            query: `@vision ${fileName}에 있는 다음 코드에 대해 설명해줘. \n\`\`\`\n${selectedText}\n\`\`\``, 
			isPartialQuery: true
        });
    });

    context.subscriptions.push(explainFileDisposable);
}

// 이 메서드는 확장 프로그램이 비활성화될 때 호출됩니다.
export function deactivate() {};

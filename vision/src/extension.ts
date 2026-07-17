// 'vscode' 모듈에는 VS Code 확장 API가 포함되어 있습니다. 이 모듈을 가져오면 편집기와 상호 작용할 수 있습니다.
import * as vscode from 'vscode';
import * as path from 'path';  		// Node.js의 path 모듈을 가져옵니다. 파일 경로를 다루는 데 사용됩니다.
import { SidebarProvider } from "./providers/sidebarProvider";	// SidebarProvider를 가져옵니다.
import { getHtmlContent } from "./openGuide";	// guideBook.html 파일을 읽어오는 함수를 가져옵니다.


// 이 메서드는 확장 프로그램이 활성화될 때 호출됩니다. 확장 프로그램이 처음으로 명령을 실행할 때 활성화됩니다.
export function activate(context: vscode.ExtensionContext) {

	// 진단 정보를 출력하거나 오류를 출력하려면 콘솔을 사용하세요. 
	// 이 코드 줄은 확장 프로그램이 활성화될 때 한 번만 실행됩니다.
	console.log('Congratulations, your extension "vision" is now active!');

	// 이 명령은 package.json 파일에 정의되어 있습니다.
	// 명령의 구현을 registerCommand로 제공합니다. 
	// commandId 매개변수는 package.json의 command 필드와 일치해야 합니다.
	const disposable = vscode.commands.registerCommand('vision.helloWorld', () => {
		// 여기에 명령이 실행될 때마다 실행되는 코드를 작성하세요
		// 사용자의 메시지 상자에 'Hello World from vision!'을 표시합니다.
		vscode.window.showInformationMessage('Hello World from vision!');
	});
	context.subscriptions.push(disposable);	// 명령을 구독에 추가하여 확장 프로그램이 비활성화될 때 정리할 수 있도록 합니다.


	//// Scenario 1. 확장 프로그램 실행 시 guideBook.html 파일을 웹뷰로 자동 실행
	// Test: F5를 눌러 확장 프로그램이 로드되는 순간, guideBook.html 내용을 웹뷰 창으로 자동 실행
	const guidepanel = vscode.window.createWebviewPanel(
		'visionGuide', 
		'Vision Guide', 
		vscode.ViewColumn.One, 
		{ 
			enableScripts: true,
			localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath))]
		}
	);
	// 프로젝트 루트에 있는 진짜 guideBook.html 파일을 읽어서 웹뷰에 주입
	guidepanel.webview.html = getHtmlContent(context);
	////

	// SidebarProvider를 등록하여 웹뷰를 표시할 수 있도록 설정
	const provider = new SidebarProvider(context.extensionUri);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            "VisionAssistant.sidebar",
            provider
        )
    );
}

// 이 메서드는 확장 프로그램이 비활성화될 때 호출됩니다.
export function deactivate() {}

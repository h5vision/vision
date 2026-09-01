import * as vscode from 'vscode';
import * as path from 'path';  		
import * as fs from "fs";
import { SidebarProvider } from "./providers/sidebarProvider";
import { GuideProvider } from "./providers/guideProvider";	
import { DependencyGraphProvider } from "./providers/dependencyGraphProvider";
import { ChatHandler } from './chat/chatHandler_AWS_server';	
import { FileDependencyProvider } from "./providers/dependencyProvider";
import { HistoryService } from './services/historyService';
import { DependencyService } from './services/dependencyService';
import { GitService } from './services/gitService';
import { CommitDiffService } from './services/commitDiffService';
import { DependencyGraphService } from './services/dependencyGraphService';
import { DependencyGraphManager } from './services/dependencyGraphManager';


// 이 메서드는 확장 프로그램이 활성화될 때 호출됩니다. 확장 프로그램이 처음으로 명령을 실행할 때 활성화됩니다.
export async function activate(context: vscode.ExtensionContext) {

	// 진단 정보를 출력하거나 오류를 출력하려면 콘솔을 사용하세요. 이 코드 줄은 확장 프로그램이 활성화될 때 한 번만 실행됩니다.
	console.log('Congratulations, your extension "vision" is now active!');

	const disposable = vscode.commands.registerCommand('vision.helloWorld', () => {
		vscode.window.showInformationMessage('Hello World from vision!');
	});
	context.subscriptions.push(disposable);


	// 커밋이 발생하면 diff를 backend 서버로 전송하는 기능을 초기화합니다.
	const gitService = new GitService();
	const commitDiffService = new CommitDiffService(gitService);
	context.subscriptions.push(gitService, commitDiffService);
	let commitId;
	gitService.initialize().then(() => {
		commitId = gitService.getCurrentCommit();
		vscode.workspace.getConfiguration('vision').update(
			"projectId",
			vscode.workspace.name || 'none',
			vscode.ConfigurationTarget.Global
		);
		vscode.workspace.getConfiguration('vision').update(
			"commitId",
			commitId,
			vscode.ConfigurationTarget.Global
		);
		commitDiffService.start();
	});

	
	const dependencyGraphService = new DependencyGraphService();
    const dependencyGraphManager = new DependencyGraphManager(dependencyGraphService, gitService);

	// SidebarProvider를 등록하여 웹뷰를 표시할 수 있도록 설정
	const provider = new SidebarProvider(context.extensionUri, dependencyGraphManager);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            "VisionAssistant.sidebar",
            provider
        )
    );

	// guideBook.html을 표시하는 GuideProvider를 등록하여 웹뷰를 표시할 수 있도록 설정
	const guideProvider = new GuideProvider(
		context,
		(message) => provider.view?.webview.postMessage(message)
	);
	context.subscriptions.push(
        vscode.commands.registerCommand(
            'vision.showGuide',
            () => guideProvider.showGuide()
        ),
		vscode.commands.registerCommand(	
            'vision.toggleGuide',
            () => guideProvider.toggleGuide()
        )
    );

	const GuideBookSetting = vscode.workspace.getConfiguration('vision').get("showGuideBook");
	console.log("GuideBookSetting:", GuideBookSetting);
	if (GuideBookSetting) {
		setTimeout(() => void vscode.commands.executeCommand('vision.showGuide').then(() => {
			console.log("Guidebook has been opened.");
			provider.view?.webview.postMessage({
				command: "guideStatus",
				data: true
			});
		}), 250);
	} else {
		provider.view?.webview.postMessage({
			command: "guideStatus",
			data: false
		});
	}
		
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

		// history.db 파일을 외부에서 열 수 있도록 명령어를 등록합니다.
		const openDBExternalCommand = vscode.commands.registerCommand('vision.openDBExternal', async () => {
			await historyService.openDBExternal();
		});
		context.subscriptions.push(openDBExternalCommand);
	} catch(err) {
		console.log(err);
	}



    // Explorer의 <v> File Dependency 탭에 전용 파일 목록 프로바이더 등록
    const dependencyProvider = new FileDependencyProvider();
	vscode.window.registerTreeDataProvider("visionFileView", dependencyProvider);

	const dependencyService = new DependencyService(dependencyProvider);

	setTimeout(() => void dependencyService.refresh(), 500);

	context.subscriptions.push(
		vscode.window.onDidChangeActiveTextEditor(() => {
			dependencyService.refresh();
		})
	);

	context.subscriptions.push(
		vscode.workspace.onDidSaveTextDocument(() => {
			dependencyService.refresh();
		})
	);


	// 우클릭하여 파일에 대한 질문 / 블록 설정한 코드에 대한 질문을 vscode chat view에 주입
	const explainFileDisposable = vscode.commands.registerCommand('vision.explainFile', async () => {
        const activeEditor = vscode.window.activeTextEditor;
        
        if (!activeEditor) {
            vscode.window.showInformationMessage('열려 있는 에디터가 없습니다.');
            return;
        }

        const selection = activeEditor.selection;
        const selectedText = activeEditor.document.getText(selection).trim();
        const fileName = path.basename(activeEditor.document.uri.fsPath);

        if (!selectedText || selectedText.length === 0) {
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

	dependencyGraphManager.initialize()
		.then(() => console.log('[DependencyGraph] Ready'))
		.catch(err => console.log('[DependencyGraph] Error',err));

	// Dependency Graph Provider 초기화
	const dependencyGraphProvider = new DependencyGraphProvider(context, dependencyGraphManager);
	context.subscriptions.push(
        vscode.commands.registerCommand(
            'vision.showDependencyGraph',
            () => dependencyGraphProvider.show()
        )
	);
}

// 이 메서드는 확장 프로그램이 비활성화될 때 호출됩니다.
export function deactivate() {};

import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

// 프로젝트 폴더의 guideBook.html 파일을 읽어와 반환하는 함수
export function getHtmlContent(
    context: vscode.ExtensionContext, 
    guidepanel: vscode.WebviewPanel
): string {

    const htmlPath = path.join(context.extensionPath, 'webview', 'guideBook.html');
    const webviewImgsFolderUri = path.join(context.extensionPath, 'webview', 'imgs');
    const imgs = fs.readdirSync(webviewImgsFolderUri);
    
    try {
        // guideBook.html 파일 내용을 읽어서 그대로 리턴
        let guideHTML = fs.readFileSync(htmlPath, 'utf8');
        for (let i in imgs) {
            let url =  vscode.Uri.joinPath(context.extensionUri, "webview", "imgs", imgs[i]);
            url = guidepanel.webview.asWebviewUri(url);
            guideHTML = guideHTML.replace(`{{${imgs[i].split('.')[0]}Url}}`, url.toString());
        }

        return guideHTML;
    } catch (error) {
        return `<!DOCTYPE html>
        <html lang="ko">
        <head><meta charset="UTF-8"><title>오류</title></head>
        <body>
            <h2>guideBook.html 파일을 찾을 수 없습니다.</h2>
            <p>경로: ${htmlPath}</p>
            <p>에러 메시지: ${error}
        </body>
        </html>`;
    };
};
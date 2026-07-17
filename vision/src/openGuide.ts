import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

// 프로젝트 폴더의 guideBook.html 파일을 읽어와 반환하는 함수
export function getHtmlContent(context: vscode.ExtensionContext): string {
    const htmlPath = path.join(context.extensionPath, 'webview', 'guideBook.html');
    
    try {
        // guideBook.html 파일 내용을 읽어서 그대로 리턴
        return fs.readFileSync(htmlPath, 'utf8');
    } catch (error) {
        return `<!DOCTYPE html>
        <html lang="ko">
        <head><meta charset="UTF-8"><title>오류</title></head>
        <body>
            <h2>guideBook.html 파일을 찾을 수 없습니다.</h2>
            <p>경로: ${htmlPath}</p>
        </body>
        </html>`;
    }
}
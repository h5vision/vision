import * as vscode from "vscode";


//// [추가 기능] 파일/폴더 색상 및 1, 2, 3 숫자 배지 표시 (FileDecorationProvider)
export class dependencyDecorationProvider implements vscode.FileDecorationProvider {
    private _onDidChangeFileDecorations = new vscode.EventEmitter<vscode.Uri | vscode.Uri[] | undefined>();
    readonly onDidChangeFileDecorations = this._onDidChangeFileDecorations.event;

    provideFileDecoration(uri: vscode.Uri): vscode.ProviderResult<vscode.FileDecoration> {
        const filePath = uri.path.toLowerCase();

        // controller: 빨강 + 숫자 '1'
        if (filePath.includes('controller')) {
            return {
                color: new vscode.ThemeColor('errorForeground'), // 빨강
                badge: '1',
                tooltip: '중요도: 높음 (빨강)'
            };
        // services: 주황 + 숫자 '2'
        } else if (filePath.includes('services')) {
            return {
                color: new vscode.ThemeColor('editorWarning.foreground'), // 주황
                badge: '2',
                tooltip: '중요도: 보통 (주황)'
            };
        // utils: 파랑 + 숫자 '3'
        } else if (filePath.includes('utils')) {
            return {
                color: new vscode.ThemeColor('charts.blue'), // 파랑 (시인성 좋음)
                badge: '3',
                tooltip: '중요도: 낮음 (파랑)'
            };
        }

        return undefined;
    }
};
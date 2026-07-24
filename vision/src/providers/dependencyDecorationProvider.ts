import * as vscode from "vscode";


//// [추가 기능] 파일/폴더 색상 및 1, 2, 3 숫자 배지 표시 (FileDecorationProvider)
export class dependencyDecorationProvider implements vscode.FileDecorationProvider {
    private _onDidChangeFileDecorations = new vscode.EventEmitter<vscode.Uri | vscode.Uri[] | undefined>();
    readonly onDidChangeFileDecorations = this._onDidChangeFileDecorations.event;

    provideFileDecoration(uri: vscode.Uri): vscode.ProviderResult<vscode.FileDecoration> {
        const filePath = uri.path.toLowerCase();

        // controller: 빨강
        // 화면에 작업 중인 파일에 대해 의존도가 높은 파일들 표시
        if (filePath.includes('controller')) {
            return {
                color: new vscode.ThemeColor('errorForeground'), // 빨강
                badge: '※',
                tooltip: '의존도 높음'
            };
        // services: 주황 + 숫자 '2'
        // } else if (filePath.includes('services')) {
        //     return {
        //         color: new vscode.ThemeColor('editorWarning.foreground'), // 주황
        //         badge: '2',
        //         tooltip: '중요도: 보통 (주황)'
        //     };
        // utils: 파랑
        // sLLM의 답변 출처가 되는 파일들을 표시
        } else if (filePath.includes('utils')) {
            return {
                color: new vscode.ThemeColor('charts.blue'), // 파랑 (시인성 좋음)
                badge: '§',
                tooltip: '답변 출처'
            };
        }

        return undefined;
    }
};
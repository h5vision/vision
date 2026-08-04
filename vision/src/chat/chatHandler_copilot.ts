import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { PromptBuilder } from "./promptBuilder";
import { HistoryService } from "../services/historyService";

export class ChatHandler {

    constructor (
        private readonly historyServcie: HistoryService
    ) {}

    public handle: vscode.ChatRequestHandler = async (
        request : vscode.ChatRequest,
        context : vscode.ChatContext,
        stream : vscode.ChatResponseStream,
        token : vscode.CancellationToken
    ) => {
        const messages = [vscode.LanguageModelChatMessage.User(PromptBuilder.build(request.prompt))];

        // get all the previous participant messages
        const previousMessages = context.history.filter(
            h => h instanceof vscode.ChatResponseTurn
        );

        // add the previous messages to the messages array
        previousMessages.forEach(m => {
            let fullMessage = '';
            m.response.forEach(r => {
                const mdPart = r as vscode.ChatResponseMarkdownPart;
                fullMessage += mdPart.value.value;
            });
            messages.push(vscode.LanguageModelChatMessage.Assistant(fullMessage));
        });


        const editor = vscode.window.activeTextEditor;
        if (editor) {
            const file = fs.readFileSync(editor.document.uri.fsPath).toString();
            messages.push(vscode.LanguageModelChatMessage.User(file));
        }
        console.log(messages);
        const dbPath = path.join(vscode.workspace.workspaceFolders?.[0].uri.fsPath || '', 'request.json');
        fs.writeFileSync(dbPath, JSON.stringify(messages, null, 2));        
        const chatresponse = await request.model.sendRequest(messages, {}, token);  

        for await (const fragment of chatresponse.text) {
            stream.markdown(fragment);
        }

    };

}
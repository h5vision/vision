import * as vscode from "vscode";
import * as fs from "fs";
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
        const messages = [vscode.LanguageModelChatMessage.User(PromptBuilder.build(""))];
        messages.push(vscode.LanguageModelChatMessage.User(request.prompt));
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            const file = fs.readFileSync(editor.document.uri.fsPath).toString();
            messages.push(vscode.LanguageModelChatMessage.User(file));
        }
        const chatresponse = await request.model.sendRequest(messages, {}, token);

        for await (const fragment of chatresponse.text) {
            stream.markdown(fragment);
        }

    };

}
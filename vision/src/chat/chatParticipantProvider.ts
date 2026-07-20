import * as vscode from "vscode";
import { ChatHandler } from "./chatHandler";

export const participant =
    vscode.chat.createChatParticipant(
        "vision.chat",
        ChatHandler.handle
    );
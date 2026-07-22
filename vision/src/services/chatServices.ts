import { APIService } from "./APIService";
import { ChatRequest, ChatResponse, ChatMessage } from "../types/chat";
import * as fs from 'fs';

export class ChatService {

    constructor( private readonly APIService: APIService ) {};

    /**
     * 사용자 메시지를 Backend로 전달
     */
    async sendMessage(request: ChatRequest): Promise<ChatResponse> {
        return await this.APIService.post(
            "/v1/chat",
            request
        ) as ChatResponse;
    };

    /**
     * Chat Request를 history에 저장
     */
    async saveHistory(content: ChatMessage) {
        
    }

};
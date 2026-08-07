import * as vscode from 'vscode';

export interface BackendStatus {
    endpoint: string;
    connected: boolean;
    message: string;
    latency: number;
}

export class APIService {

    constructor() {}

    async checkHealth(): Promise<BackendStatus> {
        const endpoint = vscode.workspace.getConfiguration().get<string>("vision.endpoint",
            "http://127.0.0.1:5000"
        )!;
        let startime = Date.now();

        try {
            const response = await fetch(`${endpoint}/health`);
            const endtime = Date.now();
            const latency = endtime - startime;
            console.log(response);
            if (!response.ok) {
                return {
                    endpoint: endpoint,
                    connected: false,
                    message: "Backend Server Error",
                    latency: -1
                };
            }
            return {
                endpoint: endpoint,
                connected: true,
                message: "Connected",
                latency: latency
            };
        }
        catch (error) {
            if (error instanceof Error) {
                return {
                    endpoint: endpoint,
                    connected: false,
                    message: error.message.toUpperCase(), 
                    latency: -1
                };
            } else {
                return {
                    endpoint: endpoint,
                    connected: false,
                    message: String(error).toUpperCase(), 
                    latency: -1
                };
            }
        }
    }

    async get(path: string) {
        const endpoint = vscode.workspace.getConfiguration().get<string>("vision.endpoint",
            "http://127.0.0.1:5000"
        )!;
        const response = await fetch(
            `${endpoint}${path}`
        );
        return response.json();
    }

    async post(path: string, body: any) {
        const endpoint = vscode.workspace.getConfiguration().get<string>("vision.endpoint",
            "http://127.0.0.1:5000"
        )!;
        const response = await fetch(
            `${endpoint}${path}`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body)
            }
        );
        console.log(response);
        return response.json();
    }

    async postStream(path: string, body: unknown, 
        onEvent: (
            event: string,
            data: Record<string, unknown>
        ) => void | Promise<void>,
        signal?: AbortSignal
    ): Promise<void> {
        const endpoint = vscode.workspace.getConfiguration().get<string>("vision.endpoint",
            "http://127.0.0.1:5000"
        )!;
        const response = await fetch(
            `${endpoint}${path}`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            },
            body: JSON.stringify(body),
            signal
        });

        if (!response.ok) {
            const raw = await response.text();
            throw new Error(
                raw || `Backend HTTP ${response.status}`
            );
        }

        const contentType =
            response.headers.get("content-type") ?? "";

        if (!contentType.includes("text/event-stream")) {
            const raw = await response.text();

            throw new Error(
                `SSE 응답이 아닙니다: ${contentType}\n${raw.slice(0, 300)}`
            );
        }

        if (!response.body) {
            throw new Error("SSE 응답 본문이 없습니다.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        const processBlock = async (
            block: string
        ): Promise<void> => {
            const lines = block.split(/\r?\n/);

            const event = lines
                .find(line => line.startsWith("event:"))
                ?.slice("event:".length)
                .trim();

            const encoded = lines
                .filter(line => line.startsWith("data:"))
                .map(line => line.slice("data:".length).trim())
                .join("\n");

            if (!event || !encoded) {
                return;
            }

            await onEvent(
                event,
                JSON.parse(encoded) as Record<string, unknown>
            );
        };

        try {
            while (true) {
                const { value, done } = await reader.read();

                if (value) {
                    buffer += decoder.decode(value, {
                        stream: true
                    });
                }

                if (done) {
                    buffer += decoder.decode();
                }

                const blocks = buffer.split(/\r?\n\r?\n/);
                buffer = blocks.pop() ?? "";

                for (const block of blocks) {
                    if (block.trim()) {
                        await processBlock(block);
                    }
                }

                if (done) {
                    if (buffer.trim()) {
                        await processBlock(buffer);
                    }

                    break;
                }
            }
        } finally {
            reader.releaseLock();
        }
    }

}
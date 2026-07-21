export interface BackendStatus {
    connected: boolean;
    message: string;
}

export class APIService {

    constructor(
        private readonly baseUrl: string = "https://api.blakeedenparker.cloud" 
    ) {}

    async checkHealth(): Promise<BackendStatus> {

        try {

            const response = await fetch(
                `${this.baseUrl}/v1/health`
            );

            if (!response.status) {

                return {
                    connected: false,
                    message: "Error"
                };

            }

            return {
                connected: true,
                message: "Connected", 
            };

        }
        catch {

            return {
                connected: false,
                message: "Offline"
            };

        }

    }

    async get(path: string) {

        const response = await fetch(
            `${this.baseUrl}${path}`
        );

        return response.json();

    }

    async post(path: string, body: any) {

        const response = await fetch(
            `${this.baseUrl}${path}`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body)
            }
        );

        return response.json();

    }

}
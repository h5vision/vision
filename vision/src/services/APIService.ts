export interface BackendStatus {
    endpoint: string;
    connected: boolean;
    message: string;
    latency: number;
}

export class APIService {

    constructor(
        private readonly baseUrl: string = "https://api.blakeedenparker.cloud" 
    ) {}

    async checkHealth(): Promise<BackendStatus> {
        let startime = Date.now();

        try {
            const response = await fetch(`${this.baseUrl}/v1/health`);
            const endtime = Date.now();
            const latency = endtime - startime;

            if (!response.status) {
                return {
                    endpoint: 'Error',
                    connected: false,
                    message: "Error",
                    latency: -1
                };
            };
            console.log(response);

            return {
                endpoint: response.url,
                connected: true,
                message: "Connected",
                latency: latency
            };

        }
        catch {

            return {
                endpoint: 'Offline',
                connected: false,
                message: "Offline", 
                latency: -1
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
export enum SidebarCommand {

    CheckBackend = "checkBackend",

    SendChat = "sendChat",

    InitialProjectIndexing = "initialProjectIndexing",

    LoadHistory = "loadHistory",

    GetProjectInfo = "getProjectInfo",

    GetProjectGitInfo = "getProjectGitInfo",

    GetGuideStatus = "getGuideStatus",

    UpdateEndpoint = "updateEndpoint",

    ToggleGuide = "toggleGuide"
}

export interface SidebarMessage {

    command: SidebarCommand;

    data?: any;

}
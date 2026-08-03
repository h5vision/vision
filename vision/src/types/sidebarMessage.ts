export enum SidebarCommand {

    CheckBackend = "checkBackend",

    SendChat = "sendChat",

    InitialProjectIndexing = "initialProjectIndexing",

    LoadHistory = "loadHistory",

    GetProjectInfo = "getProjectInfo",

    GetProjectGitInfo = "getProjectGitInfo",

    UpdateEndpoint = "updateEndpoint",

    HideGuideBook = "hideGuideBook",
    ShowGuideBook = "showGuideBook"

}

export interface SidebarMessage {

    command: SidebarCommand;

    data?: any;

}
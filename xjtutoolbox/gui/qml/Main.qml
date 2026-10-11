import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 960
    height: 720
    minimumWidth: 620
    minimumHeight: 480
    visible: true
    title: "仙交百宝箱"
    palette.window: controller.palette.window
    palette.windowText: controller.palette.windowText
    palette.base: controller.palette.base
    palette.alternateBase: controller.palette.alternateBase
    palette.text: controller.palette.text
    palette.button: controller.palette.button
    palette.buttonText: controller.palette.buttonText
    palette.toolTipBase: controller.palette.toolTipBase
    palette.toolTipText: controller.palette.toolTipText
    palette.placeholderText: controller.palette.placeholderText
    palette.disabled.text: controller.palette.disabledText
    palette.disabled.windowText: controller.palette.disabledText
    palette.disabled.buttonText: controller.palette.disabledText
    onClosing: function(close) {
        close.accepted = controller.canClose
        if (!close.accepted)
            controller.requestClose()
    }
    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            Label { text: "仙交百宝箱"; Layout.fillWidth: true }
            ComboBox {
                id: accountChoice
                model: controller.accounts
                textRole: "nickname"
                valueRole: "account_id"
                currentIndex: indexOfValue(controller.accountId)
                onActivated: controller.selectAccount(currentValue)
                Layout.preferredWidth: 220
            }
            Switch { text: "深色"; checked: controller.dark; onToggled: controller.setDark(checked) }
        }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { text: "成绩" }
            TabButton { text: "下载" }
            TabButton { text: "账户" }
        }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                RowLayout {
                    TextField { id: terms; placeholderText: "学期，例如 2025-2026-1；留空查全部"; Layout.fillWidth: true; enabled: !currentTerm.checked }
                    CheckBox { id: currentTerm; text: "当前学期" }
                    CheckBox { id: report; text: "补充成绩单" }
                    Button { text: "查询"; enabled: !controller.busy; onClicked: controller.queryScores(terms.text, currentTerm.checked, report.checked) }
                }
                Label { text: "课程 / 成绩 / 学分 / 绩点" }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: controller.rows
                    spacing: 6
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Frame {
                        required property var modelData
                        width: ListView.view.width
                        contentItem: RowLayout {
                            Label { text: modelData.courseName; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            Label { text: String(modelData.score ?? ""); Layout.preferredWidth: 80 }
                            Label { text: String(modelData.coursePoint ?? ""); Layout.preferredWidth: 60 }
                            Label { text: String(modelData.gpa ?? ""); Layout.preferredWidth: 60 }
                        }
                    }
                }
            }
            ColumnLayout {
                TextField { id: downloadUrl; placeholderText: "思源学堂附件的 HTTPS 下载地址"; Layout.fillWidth: true }
                TextField { id: destination; placeholderText: "保存文件的完整路径"; Layout.fillWidth: true }
                Button { text: "下载"; enabled: !controller.busy; onClicked: controller.download(downloadUrl.text, destination.text) }
                Item { Layout.fillHeight: true }
            }
            ColumnLayout {
                TextField { id: username; placeholderText: "用户名 / 学号"; Layout.fillWidth: true }
                TextField { id: password; placeholderText: "密码"; echoMode: TextInput.Password; Layout.fillWidth: true }
                TextField { id: nickname; placeholderText: "账户名称（可选）"; Layout.fillWidth: true }
                ComboBox { id: kind; model: ["本科生", "研究生"] }
                CheckBox { id: remember; text: "使用系统凭据存储记住密码" }
                RowLayout {
                    Button {
                        text: "添加账户"
                        onClicked: {
                            controller.addAccount(username.text, password.text, nickname.text, kind.currentIndex === 0 ? "undergraduate" : "postgraduate", remember.checked)
                            password.clear()
                        }
                    }
                    Button { text: "为选中账户输入密码"; enabled: controller.accountId !== ""; onClicked: { controller.unlock(password.text); password.clear() } }
                    Button { text: "删除选中账户"; enabled: controller.accountId !== ""; onClicked: removeDialog.open() }
                }
                Label { text: "未记住的密码仅用于本次运行，重启后需要重新输入。"; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Item { Layout.fillHeight: true }
            }
        }
        Label { text: controller.status; Layout.fillWidth: true }
        Label { text: controller.message; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            ProgressBar { Layout.fillWidth: true; from: 0; to: 100; value: Math.max(0, controller.progress); indeterminate: controller.busy && controller.progress < 0 }
            Button { text: "取消"; enabled: controller.busy; onClicked: controller.cancel() }
        }
        Frame {
            visible: controller.challenge.kind !== undefined
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                Label { text: controller.challenge.prompt ?? "" }
                Image { visible: (controller.challenge.image_base64 ?? "") !== ""; source: visible ? "data:image/png;base64," + controller.challenge.image_base64 : ""; sourceSize.height: 60 }
                RowLayout {
                    TextField { id: code; placeholderText: "验证码"; Layout.fillWidth: true }
                    Button { text: "继续"; enabled: !controller.busy; onClicked: { controller.answerChallenge(code.text); code.clear() } }
                }
            }
        }
    }
    Dialog {
        id: removeDialog
        anchors.centerIn: parent
        title: "删除账户"
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: "删除账户并取消该账户的任务？" }
        onAccepted: controller.removeAccount()
    }
}

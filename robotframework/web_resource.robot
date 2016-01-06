*** Settings ***
Documentation     A resource file with reusable keywords and variables for web interaction
...
Library           Selenium2Library
Library           Dialogs
#Suite Teardown    Close Browser

*** Variables ***
${SERVER}         10.254.240.161:8080
${BROWSER}        Chrome
${DELAY}          0
${WEB USER}       admin
${WEB PASSWORD}    tpsingtel1
${LOGIN URL}      http://${SERVER}/mremit-domestic/
${WELCOME URL}    http://${SERVER}/mremit-domestic/MainPortal.html?locale=en
${ERROR URL}      http://${SERVER}/error.html

*** Keywords ***
Open Browser and Complete Login
    Open Browser To Login Page
    Input Credentials
    Submit Credentials
    Welcome Page Should Be Open
    Web Version

Open Browser To Login Page
    Open Browser    ${LOGIN URL}    ${BROWSER}
    Set Selenium Speed    ${DELAY}
    Login Page Should Be Open

Login Page Should Be Open
    Title Should Be    Login

Go To Login Page
    Go To    ${LOGIN URL}
    Login Page Should Be Open

Input Credentials
    Input Text    username    ${WEB USER}
    Input Text    password    ${WEB PASSWORD}

Submit Credentials
    Click Element   xpath=//div[@id='isc_7']/table/tbody/tr/td[@class='buttonTitle']

Welcome Page Should Be Open
    Sleep    20s    reason=Waiting for Authentication
    Location Should Be    ${WELCOME URL}
    Title Should Be    Telepin Web

Web Version
    ${version_info}=      Version Info
    Set Suite Metadata    Web Version Info    ${version_info}    top=True

Version Info
    Click Element   xpath=//div[@id='isc_W']/table/tbody/tr/td[@class='stretchImgButton']
    ${version_info}=    Get Text    xpath=//a[@href='http://www.telepin.com/']/..
#    Log    ${version_info}
    Click Element   xpath=//img[contains(@src,'telepinwebclient/sc/skins/Graphite/images/headerIcons/close.png')]/../..
    [Return]       ${version_info}

Open Tree Group
    [Arguments]    ${tree_group_name}
    Click Element   xpath=//nobr[.='${tree_group_name}']/..
    Click Element   xpath=//nobr[.='${tree_group_name}']/..
    Sleep    2s    reason=Waiting for Group to Open

Open Tree Item
    [Arguments]    ${tree_item_name}
    Click Element   xpath=//nobr[.='${tree_item_name}']/..

Close Tab
    [Arguments]    ${tab_name}
    Click Element   xpath=//div[@eventproxy='${tab_name}']/div/table/tbody/tr/td/table/tbody/tr/td[2]
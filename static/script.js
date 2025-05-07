// static/script.js

// Wait for the DOM to be fully loaded before trying to access elements
document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chat-messages');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatbotToggleButton = document.getElementById('chatbot-toggle-button');
    const chatContainer = document.getElementById('chat-container');
    const dataDisplayArea = document.getElementById('data-display-area');

    let pendingConfirmation = null;
    let currentFormComponent = null;

    if (chatbotToggleButton) {
        chatbotToggleButton.addEventListener('click', () => {
            chatContainer.classList.toggle('open');
            if (chatContainer.classList.contains('open')) {
                chatbotToggleButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
                if(messageInput) messageInput.focus();
            } else {
                chatbotToggleButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
            }
        });
    }


    function addMessage(text, sender, type = '') {
        if (!chatMessages) return null; // Guard against missing element

        const messageElement = document.createElement('div');
        messageElement.classList.add('message', sender);
        if (type) messageElement.classList.add(type);

        if (sender === 'bot' && (type === 'confirmation' || text.includes('`') || text.toLowerCase().includes("query is:") || text.toLowerCase().includes("attempted:"))) {
             const preElement = document.createElement('pre');
             preElement.textContent = text.replace(/`/g, '');
             messageElement.appendChild(preElement);
        } else {
            messageElement.textContent = text;
        }
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return messageElement;
    }

    function displayThinkingIndicator(show) {
        if (!chatMessages) return;
        let thinkingMsg = document.querySelector('.message.bot.thinking');
        if (show) {
            if (!thinkingMsg) thinkingMsg = addMessage("", 'bot', 'thinking');
        } else {
            if (thinkingMsg) thinkingMsg.remove();
        }
    }

    async function callChatAPI(payload) {
        displayThinkingIndicator(true);
        try {
            const response = await fetch('/chat', { // This path is relative to the domain
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            displayThinkingIndicator(false);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `Server error: ${response.status} ${response.statusText}` }));
                throw new Error(errorData.error || `Server error: ${response.status} ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            displayThinkingIndicator(false);
            console.error("API Call error:", error);
            addMessage(`Network or Server Error: ${error.message}`, 'bot', 'error');
            throw error;
        }
    }

    async function handleUserMessage(messageText) {
        if (!messageText) return;
        addMessage(messageText, 'user');
        if (messageInput) messageInput.value = '';

        try {
            const data = await callChatAPI({ message: messageText });
            processApiResponse(data, messageText);
        } catch (error) { /* Error already displayed by callChatAPI */ }
        if (chatContainer && chatContainer.classList.contains('open') && messageInput) messageInput.focus();
    }

    function processApiResponse(data, originalUserMessage = "Operation") {
        if (!data || !data.type) {
            addMessage("Received an invalid response from the server.", "bot", "error");
            console.error("Invalid API response:", data);
            return;
        }
        clearDataDisplayAreaIfNecessary(data.type);

        switch (data.type) {
            case "LOAD_COMPONENT":
                addMessage(data.response_text, 'bot', 'info');
                if (data.component_name === "add_employee_form") {
                    loadAddEmployeeFormComponent(data.pre_fill_data || {});
                }
                break;
            case "CONFIRMATION_REQUIRED":
                pendingConfirmation = {
                    query_to_confirm: data.query_to_confirm,
                    query_type_to_confirm: data.query_type_to_confirm,
                    original_user_message: originalUserMessage
                };
                const confirmMsgElement = addMessage(data.response_text, 'bot', 'confirmation');
                if(confirmMsgElement) renderConfirmationButtons(confirmMsgElement);
                break;
            case "DATA_RESULT":
                addMessage(data.response_text, 'bot', 'info');
                displayDataTableOnPage(data.data, data.query_executed, originalUserMessage);
                break;
            case "ACTION_SUCCESS":
                addMessage(data.response_text, 'bot', 'success');
                if (data.query_executed) addMessage(`Executed: ${data.query_executed}`, 'bot', 'info');
                if(dataDisplayArea) {
                    dataDisplayArea.innerHTML = `<div class="dynamic-form-container" style="text-align:center; padding: 30px; color:var(--hr-success-color); font-size: 1.1em;"><p>${data.response_text}</p></div>`;
                    dataDisplayArea.style.opacity = 1;
                }
                break;
            case "FORM_ERROR":
            case "EXECUTION_ERROR":
            case "ERROR":
                addMessage(data.response_text || "An error occurred.", 'bot', 'error');
                if (data.query_attempted) addMessage(`Attempted Query: ${data.query_attempted}`, 'bot', 'info');
                 if(dataDisplayArea) {
                    dataDisplayArea.innerHTML = `<div class="dynamic-form-container" style="text-align:center; padding: 30px; color:var(--hr-error-color); font-size: 1.1em;"><p>${data.response_text || "An error occurred."}</p></div>`;
                    dataDisplayArea.style.opacity = 1;
                 }
                break;
            case "CLARIFICATION":
            case "CHAT":
                addMessage(data.response_text, 'bot', 'info');
                break;
            default:
                addMessage(`Received an unexpected response type: ${data.type || 'Unknown type'} from the server.`, 'bot', 'error');
        }
    }

    function renderConfirmationButtons(messageElement) {
        const buttonsDiv = document.createElement('div');
        buttonsDiv.classList.add('confirmation-buttons');
        const yesButton = document.createElement('button');
        yesButton.textContent = 'Yes, Proceed';
        yesButton.onclick = async () => {
            const preElement = messageElement.querySelector('pre');
            if (preElement) {
                 messageElement.innerHTML = `<pre>${preElement.textContent}</pre><br><b>User confirmed. Executing...</b>`;
            } else {
                 messageElement.innerHTML += "<br><b>User confirmed. Executing...</b>";
            }
            buttonsDiv.remove();
            try {
                const data = await callChatAPI({
                    message: pendingConfirmation.original_user_message,
                    confirmed_execution: true,
                    confirmed_sql_query: pendingConfirmation.query_to_confirm,
                    confirmed_query_type: pendingConfirmation.query_type_to_confirm
                });
                processApiResponse(data, pendingConfirmation.original_user_message);
            } catch (error) { /* Handled by callChatAPI */ }
            pendingConfirmation = null;
        };
        const noButton = document.createElement('button');
        noButton.classList.add('confirm-no');
        noButton.textContent = 'No, Cancel';
        noButton.onclick = () => {
            addMessage("Operation cancelled.", 'bot', 'info');
            buttonsDiv.remove();
            pendingConfirmation = null;
        };
        buttonsDiv.appendChild(yesButton);
        buttonsDiv.appendChild(noButton);
        messageElement.appendChild(buttonsDiv);
    }

    function clearDataDisplayAreaIfNecessary(responseType) {
        if (!dataDisplayArea) return;
        const typesToClearFor = ["DATA_RESULT", "LOAD_COMPONENT", "FORM_ERROR", "EXECUTION_ERROR", "ACTION_SUCCESS"];
        if (typesToClearFor.includes(responseType) || currentFormComponent) {
            dataDisplayArea.innerHTML = '';
            dataDisplayArea.style.opacity = 0;
            currentFormComponent = null;
        }
    }

    function loadAddEmployeeFormComponent(preFillData = {}) {
        if (!dataDisplayArea) return;
        clearDataDisplayAreaIfNecessary("LOAD_COMPONENT");
        currentFormComponent = "add_employee_form";

        const formContainer = document.createElement('div');
        formContainer.classList.add('dynamic-form-container');
        // Using current date in YYYY-MM-DD for hire_date default
        const today = new Date().toISOString().split('T')[0];

        formContainer.innerHTML = `
            <h3>Add New Employee Record</h3>
            <form id="add-employee-form">
                <div class="form-group">
                    <label for="emp-first-name">First Name*</label>
                    <input type="text" id="emp-first-name" name="first_name" value="${preFillData.first_name || ''}" required>
                </div>
                <div class="form-group">
                    <label for="emp-last-name">Last Name*</label>
                    <input type="text" id="emp-last-name" name="last_name" value="${preFillData.last_name || ''}" required>
                </div>
                <div class="form-group">
                    <label for="emp-email">Email*</label>
                    <input type="email" id="emp-email" name="email" value="${preFillData.email || ''}" required>
                </div>
                <div class="form-group">
                    <label for="emp-phone">Phone Number</label>
                    <input type="text" id="emp-phone" name="phone_number" value="${preFillData.phone_number || ''}">
                </div>
                <div class="form-group">
                    <label for="emp-hire-date">Hire Date*</label>
                    <input type="date" id="emp-hire-date" name="hire_date" value="${preFillData.hire_date || today}" required>
                </div>
                <div class="form-group">
                    <label for="emp-job-id">Job ID</label>
                    <input type="text" id="emp-job-id" name="job_id" value="${preFillData.job_id || ''}">
                </div>
                <div class="form-group">
                    <label for="emp-salary">Salary*</label>
                    <input type="number" id="emp-salary" name="salary" step="0.01" value="${preFillData.salary || ''}" required>
                </div>
                <div class="form-group">
                    <label for="emp-commission">Commission Pct (e.g., 0.1 for 10%)</label>
                    <input type="number" id="emp-commission" name="commission_pct" step="0.01" min="0" max="1" value="${preFillData.commission_pct || ''}">
                </div>
                <div class="form-group">
                    <label for="emp-manager-id">Manager ID</label>
                    <input type="number" id="emp-manager-id" name="manager_id" value="${preFillData.manager_id || ''}">
                </div>
                <div class="form-group">
                    <label for="emp-department-id">Department ID</label>
                    <input type="number" id="emp-department-id" name="department_id" value="${preFillData.department_id || ''}">
                </div>
                <div class="form-actions">
                    <button type="submit">Add Employee Record</button>
                </div>
            </form>
        `;
        dataDisplayArea.appendChild(formContainer);
        setTimeout(() => dataDisplayArea.style.opacity = 1, 50);

        const form = formContainer.querySelector('#add-employee-form');
        if (form) {
            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                const formData = new FormData(form);
                const employeeData = {};
                
                // Basic client-side validation for required fields
                if (!formData.get('first_name') || !formData.get('last_name') || !formData.get('email') || !formData.get('hire_date') || !formData.get('salary')) {
                    addMessage("Please fill in all required fields (*) for the new employee.", "bot", "error");
                    // Optionally, highlight missing fields in the form
                    return;
                }

                formData.forEach((value, key) => {
                    employeeData[key] = value ? value : null; // Send null for empty optional fields
                });
                
                addMessage("Submitting new employee data via form...", 'user');
                try {
                    const data = await callChatAPI({ add_employee_form_data: employeeData });
                    processApiResponse(data, "Add New Employee (Form Submission)");
                } catch (error) { /* Handled by callChatAPI */ }
            });
        }
    }

    function displayDataTableOnPage(data, queryExecuted, userQuery) {
        if (!dataDisplayArea) return;
        dataDisplayArea.innerHTML = '';
        dataDisplayArea.style.opacity = 0;

        if (!data || data.length === 0) {
            const noDataMessage = document.createElement('p');
            noDataMessage.textContent = "No data found for your query.";
            noDataMessage.style.textAlign = 'center';
            noDataMessage.style.padding = '20px';
            noDataMessage.style.color = 'var(--hr-text-color)';
            dataDisplayArea.appendChild(noDataMessage);
            if (queryExecuted) addExecutedQueryToPage(queryExecuted, userQuery);
            setTimeout(() => dataDisplayArea.style.opacity = 1, 50);
            return;
        }

        const title = document.createElement('h3');
        title.classList.add('table-title');
        title.textContent = `Query Results: "${userQuery}"`;
        dataDisplayArea.appendChild(title);

        const tableContainer = document.createElement('div');
        tableContainer.classList.add('data-table-container');

        const table = document.createElement('table');
        table.classList.add('styled-table');

        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        Object.keys(data[0]).forEach(key => {
            const th = document.createElement('th');
            th.textContent = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        data.forEach(rowData => {
            const tr = document.createElement('tr');
            Object.values(rowData).forEach(value => {
                const td = document.createElement('td');
                td.textContent = value !== null ? String(value) : 'N/A';
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        tableContainer.appendChild(table);
        dataDisplayArea.appendChild(tableContainer);
        if (queryExecuted) addExecutedQueryToPage(queryExecuted, userQuery, tableContainer);
        
        setTimeout(() => dataDisplayArea.style.opacity = 1, 50);
    }

    function addExecutedQueryToPage(query, userQuery, parentElement = dataDisplayArea) {
        if (!parentElement) return;
        if (parentElement !== dataDisplayArea && !parentElement.classList.contains('data-table-container')) {
             return;
        }
        const queryWrapper = document.createElement('div');
        queryWrapper.classList.add('executed-query-wrapper');
        const p = document.createElement('p');
        p.textContent = "Query executed:";
        queryWrapper.appendChild(p);
        const pre = document.createElement('pre');
        pre.classList.add('executed-query-text');
        pre.textContent = query;
        queryWrapper.appendChild(pre);
        parentElement.appendChild(queryWrapper);
    }

    // Initial setup for event listeners if elements exist
    if (sendButton && messageInput) {
        sendButton.addEventListener('click', () => handleUserMessage(messageInput.value.trim()));
        messageInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                handleUserMessage(messageInput.value.trim());
            }
        });
    } else {
        console.error("Chat input elements not found!");
    }
}); // End of DOMContentLoaded
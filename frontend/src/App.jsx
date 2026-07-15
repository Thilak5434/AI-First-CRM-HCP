import React, { useState, useEffect, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import {
  Calendar, Clock, Users, FileText, Plus, X, Search, Send,
  History, ShieldAlert, Sparkles, RefreshCw, AlertCircle, CheckCircle
} from 'lucide-react'
import {
  setFormField, updateFormState, resetForm, addChatMessage,
  setHcpList, setInteractionsList, setComplianceReport,
  setProposedForm, setProposedComplianceReport, clearProposed,
  setLoading, setError, setToast, clearToast
} from './store'

function App() {
  const dispatch = useDispatch()
  const {
    currentForm, hcpList, interactionsList, chatMessages,
    complianceReport, proposedForm, proposedComplianceReport, loading, toast
  } = useSelector((state) => state.crm)

  // Local UI states
  const [chatInput, setChatInput] = useState('')
  const [hcpSearchVal, setHcpSearchVal] = useState('')
  const [showHcpDropdown, setShowHcpDropdown] = useState(false)
  const [attendeeInput, setAttendeeInput] = useState('')
  const [materialInput, setMaterialInput] = useState('')
  const chatEndRef = useRef(null)
  // Fetch initial data
  const fetchData = async () => {
    try {
      // Fetch HCP List
      const hcpRes = await fetch('/api/hcps')
      if (hcpRes.ok) {
        const hcps = await hcpRes.json()
        dispatch(setHcpList(hcps))
      }
      // Fetch Interactions List
      const interRes = await fetch('/api/interactions')
      if (interRes.ok) {
        const interactions = await interRes.json()
        dispatch(setInteractionsList(interactions))
      }
    } catch (err) {
      console.error("Error fetching initial data: ", err)
      showNotification('warning', 'Failed to connect to backend server. Ensure backend is running.')
    }
  }
  useEffect(() => {
    fetchData()
  }, [])
  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])
  // Toast auto-dismiss
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => {
        dispatch(clearToast())
      }, 5000)
      return () => clearTimeout(timer)
    }
  }, [toast])
  const showNotification = (type, message) => {
    dispatch(setToast({ type, message }))
  }
  // Handle Form field changes
  const handleInputChange = (field, value) => {
    dispatch(setFormField({ field, value }))
  }
  // Tags/Badges Add/Remove for Attendees
  const addAttendee = (name) => {
    const cleaned = name.trim()
    if (cleaned && !currentForm.attendees.includes(cleaned)) {
      dispatch(setFormField({
        field: 'attendees',
        value: [...currentForm.attendees, cleaned]
      }))
    }
    setAttendeeInput('')
  }
  const removeAttendee = (index) => {
    const updated = [...currentForm.attendees]
    updated.splice(index, 1)
    dispatch(setFormField({ field: 'attendees', value: updated }))
  }
  // Tags/Badges Add/Remove for Materials Shared
  const addMaterial = (name) => {
    const cleaned = name.trim()
    if (cleaned && !currentForm.materials_shared.includes(cleaned)) {
      dispatch(setFormField({
        field: 'materials_shared',
        value: [...currentForm.materials_shared, cleaned]
      }))
    }
    setMaterialInput('')
  }
  const removeMaterial = (index) => {
    const updated = [...currentForm.materials_shared]
    updated.splice(index, 1)
    dispatch(setFormField({ field: 'materials_shared', value: updated }))
  }
  const selectQuickMaterial = (material) => {
    if (!currentForm.materials_shared.includes(material)) {
      dispatch(setFormField({
        field: 'materials_shared',
        value: [...currentForm.materials_shared, material]
      }))
    }
  }
  // Submit form manually (Structured logging)
  const handleSubmitForm = async (e) => {
    e.preventDefault()
    if (!currentForm.hcp_id && !currentForm.hcp_name) {
      showNotification('warning', 'Please select or type an HCP Name.')
      return
    }
    dispatch(setLoading(true))
    try {
      let response
      if (currentForm.id) {
        // Edit Mode
        response = await fetch(`/api/interactions/${currentForm.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            interaction_type: currentForm.interaction_type,
            date: currentForm.date,
            time: currentForm.time,
            attendees: currentForm.attendees,
            topics_discussed: currentForm.topics_discussed,
            materials_shared: currentForm.materials_shared,
            sentiment: currentForm.sentiment
          })
        })
      } else {
        // Log Mode
        response = await fetch('/api/interactions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            hcp_id: Number(currentForm.hcp_id) || 0,
            interaction_type: currentForm.interaction_type,
            date: currentForm.date,
            time: currentForm.time,
            attendees: currentForm.attendees,
            topics_discussed: currentForm.topics_discussed,
            materials_shared: currentForm.materials_shared,
            sentiment: currentForm.sentiment
          })
        })
      }
      if (response.ok) {
        showNotification('success', currentForm.id ? 'Interaction updated successfully!' : 'Interaction logged successfully!')
        dispatch(resetForm())
        dispatch(clearProposed())
        // Re-fetch interactions list
        const listRes = await fetch('/api/interactions')
        if (listRes.ok) {
          const list = await listRes.json()
          dispatch(setInteractionsList(list))
        }
      } else {
        const errorData = await response.json()
        showNotification('warning', `Error: ${errorData.detail || 'Failed to save interaction.'}`)
      }
    } catch (err) {
      console.error(err)
      showNotification('warning', 'Network error. Could not connect to API.')
    } finally {
      dispatch(setLoading(false))
    }
  }
  // Fill form from history (for editing/reviewing)
  const handleLoadHistory = (item) => {
    // Find matching hcp_id if not present
    const hcp = hcpList.find(h => h.name.toLowerCase() === item.hcp_name.toLowerCase())
    dispatch(updateFormState({
      id: item.id,
      hcp_id: hcp ? hcp.id : '',
      hcp_name: item.hcp_name,
      interaction_type: item.interaction_type,
      date: item.date,
      time: item.time,
      attendees: item.attendees,
      topics_discussed: item.topics_discussed,
      materials_shared: item.materials_shared,
      sentiment: item.sentiment
    }))
    
    // Fetch compliance report for loaded history item
    checkComplianceLocal(item.topics_discussed, item.materials_shared)
    showNotification('success', `Loaded interaction with ${item.hcp_name} into editor.`)
  }
  // Trigger compliance check manually or automatically on text change
  const checkComplianceLocal = async (topics, materials) => {
    if (!topics.trim()) return
    try {
      const res = await fetch('/api/compliance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topics_discussed: topics, materials_shared: materials })
      })
      if (res.ok) {
        const report = await res.json()
        dispatch(setComplianceReport(report))
      }
    } catch (e) {
      console.error(e)
    }
  }
  useEffect(() => {
    // Debounce compliance checking on topics typing
    const delayDebounce = setTimeout(() => {
      checkComplianceLocal(currentForm.topics_discussed, currentForm.materials_shared)
    }, 1000)
    return () => clearTimeout(delayDebounce)
  }, [currentForm.topics_discussed, currentForm.materials_shared])
  // AI Chat submission (Conversational logging)
  const handleSendChatMessage = async (e) => {
    e.preventDefault()
    if (!chatInput.trim()) return
    const userMessage = chatInput
    setChatInput('')
    // Append user message to Redux chat message list
    dispatch(addChatMessage({ role: 'user', content: userMessage }))
    dispatch(setLoading(true))
    // Form current form state for LLM context
    const currentFormContext = {
      hcp_name: currentForm.hcp_name,
      hcp_id: currentForm.hcp_id,
      interaction_type: currentForm.interaction_type,
      date: currentForm.date,
      time: currentForm.time,
      attendees: currentForm.attendees,
      topics_discussed: currentForm.topics_discussed,
      materials_shared: currentForm.materials_shared,
      sentiment: currentForm.sentiment
    }
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
          message: userMessage,
          // IMPORTANT: backend expects history items shaped as {role, content} only.
          // Do not send UI-only fields like tools_executed.
          history: chatMessages.map(m => ({ role: m.role, content: m.content })),
          current_form: currentFormContext
        })

      })
      if (response.ok) {
        const data = await response.json()
        
        // Append AI reply
        dispatch(addChatMessage({
          role: 'assistant',
          content: data.reply,
          tools_executed: data.tools_executed
        }))

        // Store AI extraction as a proposal for the user to review
        if (data.proposed_form && Object.keys(data.proposed_form).length > 0) {
          dispatch(setProposedForm(data.proposed_form))
        } else {
          dispatch(setProposedForm({}))
        }
        if (data.proposed_compliance_report) {
          dispatch(setProposedComplianceReport(data.proposed_compliance_report))
        } else {
          dispatch(setProposedComplianceReport(null))
        }

        // IMPORTANT: log_interaction / edit_interaction write straight to the DB on the
        // backend as soon as the agent calls them - by the time we get this response the
        // row already exists (or was changed). We MUST sync currentForm.id to that row now.
        // Otherwise the left-hand form still holds whatever stale data was in it before this
        // chat message, and if the user then clicks "Save"/"Log Interaction", it re-submits
        // that stale data as a brand-new duplicate row instead of touching the record the AI
        // just created. Auto-applying here means a later manual Save safely edits the same
        // row (or is simply a no-op), never a duplicate.
        if (data.tools_executed?.some(t => ['log_interaction', 'edit_interaction'].includes(t))) {
          if (data.proposed_form && data.proposed_form.id) {
            dispatch(updateFormState(data.proposed_form))
            if (data.proposed_compliance_report) {
              dispatch(setComplianceReport(data.proposed_compliance_report))
            }
          }
          try {
            const [hcpRes, interRes] = await Promise.all([
              fetch('/api/hcps'),
              fetch('/api/interactions')
            ])
            if (hcpRes.ok) {
              dispatch(setHcpList(await hcpRes.json()))
            }
            if (interRes.ok) {
              dispatch(setInteractionsList(await interRes.json()))
            }
          } catch (refreshErr) {
            console.error('Failed to refresh lists after AI tool execution: ', refreshErr)
          }
        }

      } else {
        const errorData = await response.json()
        const detail = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail ?? errorData)
        dispatch(addChatMessage({
          role: 'assistant',
          content: `Failed to invoke AI: ${detail || 'Server error'}`
        }))
      }

    } catch (err) {
      console.error(err)
      dispatch(addChatMessage({
        role: 'assistant',
        content: "Network error. Make sure the FastAPI backend is running."
      }))
    } finally {
      dispatch(setLoading(false))
    }
  }
  // Handle HCP select autocomplete
  const handleHcpSearchChange = (val) => {
    setHcpSearchVal(val)
    if (val.trim()) {
      setShowHcpDropdown(true)
    } else {
      setShowHcpDropdown(false)
    }
    // Also set currentForm hcp_name directly if typing a new doctor
    dispatch(updateFormState({ hcp_name: val, hcp_id: '' }))
  }
  const selectHcpFromSearch = (hcp) => {
    dispatch(updateFormState({
      hcp_id: hcp.id,
      hcp_name: hcp.name,
      attendees: [...new Set([...currentForm.attendees, hcp.name, 'Alex Rivera (Rep)'])]
    }))
    setHcpSearchVal(hcp.name)
    setShowHcpDropdown(false)
  }
  // Quick materials list for Life Science reps
  const quickMaterials = [
    "Prodo-X Brochure",
    "Safety Study Reprint",
    "Product Monograph",
    "Efficacy Presentation",
    "Sample Pack (Vials x5)",
    "HCP Patient Guide"
  ]
  return (
    <div className="app-container">
      {/* Toast Notification */}
      {toast && (
        <div className={`toast-notification ${toast.type === 'warning' ? 'warning' : ''}`}>
          {toast.type === 'warning' ? <AlertCircle size={20} className="text-warning" /> : <CheckCircle size={20} className="text-success" />}
          <span>{toast.message}</span>
        </div>
      )}
      {/* Header */}
      <header className="app-header">
        <div className="logo-section">
          <span className="logo-icon">🏥</span>
          <div className="logo-text">
            <h1>AI-First Life Science CRM</h1>
            <p>HCP Field Representative Module</p>
          </div>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={fetchData}>
            <RefreshCw size={14} /> Refresh Data
          </button>
        </div>
      </header>
      {/* Workspace Grid */}
      <div className="workspace-grid">
        
        {/* Left Panel: Log HCP Interaction Form */}
        <section className="glass-panel">
          <div className="panel-header">
            <h2 className="panel-title">
              <FileText size={18} className="text-primary" />
              {currentForm.id ? `Edit Interaction (#${currentForm.id})` : 'Log HCP Interaction'}
            </h2>
          </div>
          <form onSubmit={handleSubmitForm} className="form-scrollable" style={{ paddingBottom: '0.6rem' }}>

            {/* Proposed extraction (AI) */}
            {proposedForm && Object.keys(proposedForm).length > 0 && (
              <div style={{ marginBottom: '1rem', padding: '0.75rem', border: '1px dashed var(--input-border)', borderRadius: '10px', background: 'rgba(96, 165, 250, 0.06)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>AI Proposed Changes</div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem' }}
                    onClick={() => {
                      dispatch(updateFormState(proposedForm))
                      if (proposedComplianceReport) {
                        dispatch(setComplianceReport(proposedComplianceReport))
                      }
                      showNotification('success', 'Proposed changes applied to the form.')
                    }}
                  >
                    Apply proposed changes
                  </button>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  <div><b>HCP</b>: {proposedForm.hcp_name || '-'}</div>
                  <div><b>Date</b>: {proposedForm.date || '-'}</div>
                  <div><b>Time</b>: {proposedForm.time || '-'}</div>
                  <div><b>Type</b>: {proposedForm.interaction_type || '-'}</div>
                  <div><b>Sentiment</b>: {proposedForm.sentiment || '-'}</div>
                  <div><b>Topics</b>: {proposedForm.topics_discussed ? proposedForm.topics_discussed.slice(0, 140) : '-'}</div>
                </div>
              </div>
            )}

            {/* HCP Name & Interaction Type */}
            <div className="form-grid-2">
              <div className="form-group" style={{ position: 'relative' }}>
                <label className="form-label">HCP Name</label>
                <div style={{ display: 'flex', alignItems: 'center', background: 'var(--input-bg)', border: '1px solid var(--input-border)', borderRadius: '8px' }}>
                  <Search size={16} style={{ marginLeft: '10px', color: 'var(--text-secondary)' }} />
                  <input
                    type="text"
                    className="form-input"
                    style={{ border: 'none', background: 'transparent', flex: 1, paddingLeft: '8px' }}
                    placeholder="Search or type HCP..."
                    value={hcpSearchVal || currentForm.hcp_name}
                    onChange={(e) => handleHcpSearchChange(e.target.value)}
                    onFocus={() => setShowHcpDropdown(true)}
                  />
                </div>
                {showHcpDropdown && hcpList.length > 0 && (
                  <div className="search-results-dropdown">
                    {hcpList
                      .filter(h => h.name.toLowerCase().includes(hcpSearchVal.toLowerCase()))
                      .map(hcp => (
                        <div
                          key={hcp.id}
                          className="search-item"
                          onClick={() => selectHcpFromSearch(hcp)}
                        >
                          <strong>{hcp.name}</strong> - {hcp.specialty} ({hcp.hospital})
                        </div>
                      ))
                    }
                  </div>
                )}
              </div>
              <div className="form-group">
                <label className="form-label">Interaction Type</label>
                <select
                  className="form-select"
                  value={currentForm.interaction_type}
                  onChange={(e) => handleInputChange('interaction_type', e.target.value)}
                >
                  <option value="Meeting">Meeting</option>
                  <option value="Call">Call</option>
                  <option value="Email">Email</option>
                  <option value="Webcast">Webcast</option>
                </select>
              </div>
            </div>
            {/* Date & Time */}
            <div className="form-grid-2">
              <div className="form-group">
                <label className="form-label">Date</label>
                <div style={{ display: 'flex', alignItems: 'center', background: 'var(--input-bg)', border: '1px solid var(--input-border)', borderRadius: '8px', paddingRight: '10px' }}>
                  <input
                    type="date"
                    className="form-input"
                    style={{ border: 'none', background: 'transparent', flex: 1 }}
                    value={currentForm.date}
                    onChange={(e) => handleInputChange('date', e.target.value)}
                  />
                  <Calendar size={16} style={{ color: 'var(--text-secondary)' }} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Time</label>
                <div style={{ display: 'flex', alignItems: 'center', background: 'var(--input-bg)', border: '1px solid var(--input-border)', borderRadius: '8px', paddingRight: '10px' }}>
                  <input
                    type="time"
                    className="form-input"
                    style={{ border: 'none', background: 'transparent', flex: 1 }}
                    value={currentForm.time}
                    onChange={(e) => handleInputChange('time', e.target.value)}
                  />
                  <Clock size={16} style={{ color: 'var(--text-secondary)' }} />
                </div>
              </div>
            </div>
            {/* Attendees */}
            <div className="form-group">
              <label className="form-label">Attendees</label>
              <div className="tags-container">
                {currentForm.attendees.map((att, idx) => (
                  <span key={idx} className="tag-badge">
                    {att}
                    <button type="button" className="tag-close" onClick={() => removeAttendee(idx)}>
                      <X size={12} />
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  placeholder="Enter name & press Enter..."
                  className="tag-input-inline"
                  value={attendeeInput}
                  onChange={(e) => setAttendeeInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addAttendee(attendeeInput)
                    }
                  }}
                />
              </div>
            </div>
            {/* Topics Discussed */}
            <div className="form-group">
              <label className="form-label">Topics Discussed</label>
              <textarea
                className="form-textarea"
                placeholder="Enter details of discussions (efficacy, safety indicators, side effects, study data...)"
                value={currentForm.topics_discussed}
                onChange={(e) => handleInputChange('topics_discussed', e.target.value)}
              />
            </div>
            {/* Materials Shared */}
            <div className="form-group">
              <label className="form-label">Materials Shared / Samples Distributed</label>
              <div className="tags-container" style={{ marginBottom: '0.5rem' }}>
                {currentForm.materials_shared.map((mat, idx) => (
                  <span key={idx} className="tag-badge" style={{ backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#a7f3d0', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                    {mat}
                    <button type="button" className="tag-close" onClick={() => removeMaterial(idx)}>
                      <X size={12} style={{ color: '#a7f3d0' }} />
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  placeholder="Type material & press Enter..."
                  className="tag-input-inline"
                  value={materialInput}
                  onChange={(e) => setMaterialInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addMaterial(materialInput)
                    }
                  }}
                />
              </div>
              
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', fontWeight: 500 }}>
                Quick Add Materials:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                {quickMaterials.map(m => (
                  <button
                    key={m}
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: '0.2rem 0.6rem', fontSize: '0.7rem', borderRadius: '4px' }}
                    onClick={() => selectQuickMaterial(m)}
                  >
                    + {m}
                  </button>
                ))}
              </div>
            </div>
            {/* Sentiment Selector */}
            <div className="form-group">
              <label className="form-label">Sentiment</label>
              <div className="sentiment-selector">
                {['Positive', 'Neutral', 'Negative'].map((s) => (
                  <label key={s} className="sentiment-radio">
                    <input
                      type="radio"
                      name="sentiment"
                      value={s}
                      checked={currentForm.sentiment === s}
                      onChange={() => handleInputChange('sentiment', s)}
                    />
                    {s}
                  </label>
                ))}
              </div>
            </div>
            {/* Form actions */}
            <div className="form-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  dispatch(resetForm())
                  setHcpSearchVal('')
                }}
              >
                Clear
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading}
              >
                {currentForm.id ? 'Save Updates' : 'Log Interaction'}
              </button>
            </div>


          </form>
          {/* Recent History (Footer) */}
          <div className="recent-history-section" style={{ marginTop: '2rem' }}>
            <h3 className="history-title">
              <History size={14} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'text-bottom' }} /> 
              Recent Logged Interactions ({interactionsList.length})
            </h3>
            <div className="history-list">
              {interactionsList.length === 0 ? (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                  No logged interactions in database yet.
                </div>
              ) : (
                interactionsList.map((item) => (
                  <div
                    key={item.id}
                    className="history-card"
                    onClick={() => handleLoadHistory(item)}
                  >
                    <div className="history-card-header">
                      <span className="history-card-name">{item.hcp_name}</span>
                      <span className="history-card-meta">
                        <span className={`sentiment-indicator ${item.sentiment.toLowerCase()}`} style={{ marginRight: '6px' }}></span>
                        {item.date} • {item.interaction_type}
                      </span>
                    </div>
                    <div className="history-card-topics">{item.topics_discussed}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
        {/* Right Panel: AI Assistant */}
        <section className="glass-panel">
          <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 className="panel-title">
              <Sparkles size={18} style={{ color: '#60a5fa' }} />
              AI CRM Assistant
            </h2>
            <button
              className="btn btn-secondary"
              style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}
              onClick={() => {
                dispatch(updateFormState({ id: null })) // Reset edit mode
                dispatch(resetForm())
                showNotification('success', 'Reset editor context.')
              }}
            >
              Start New Flow
            </button>
          </div>
          <div className="chat-container">
            {/* Message window */}
            <div className="chat-history">
              {chatMessages.map((msg, idx) => (
                <div key={idx} style={{ display: 'flex', flexDirection: 'column', alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', width: '100%' }}>
                  <div className={`message-bubble ${msg.role}`}>
                    {msg.content}
                    
                    {/* Render tool execution tags if present */}
                    {msg.tools_executed && msg.tools_executed.length > 0 && (
                      <div className="tools-executed-container">
                        <span style={{ color: 'var(--text-secondary)', marginRight: '2px' }}>Executed Tools:</span>
                        {msg.tools_executed.map((t) => (
                          <span key={t} className="tool-badge">
                            ⚙️ {t}
                          </span>
                        ))}
                      </div>
                    )}
                    
                    {/* Render compliance warning inside chat thread if present */}
                    {msg.compliance_report && msg.compliance_report.status === 'WARNING' && (
                      <div className="compliance-warning-card">
                        <span className="compliance-warning-header">
                          <ShieldAlert size={14} /> Pharma Compliance Warning
                        </span>
                        {msg.compliance_report.warnings.map((w, wIdx) => (
                          <div key={wIdx}>• {w}</div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="message-bubble assistant" style={{ fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <RefreshCw size={14} style={{ animation: 'spin 1.5s linear infinite' }} /> Processing with LangGraph agent...
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            {/* Direct Compliance Notification overlay if form violates compliance */}
            {complianceReport && complianceReport.status === 'WARNING' && (
              <div className="compliance-warning-card" style={{ marginBottom: '1rem', marginTop: '0px' }}>
                <span className="compliance-warning-header">
                  <ShieldAlert size={15} /> Real-time Compliance Analysis (Active Form)
                </span>
                {complianceReport.warnings.map((w, idx) => (
                  <div key={idx} style={{ fontSize: '0.75rem' }}>• {w}</div>
                ))}
              </div>
            )}
            {/* Chat Input form */}
            <form onSubmit={handleSendChatMessage} className="chat-input-bar">
              <textarea
                className="chat-textarea"
                placeholder="Talk to AI (e.g. 'search Dr. Sarah', 'show history of Dr. Sarah Jenkins', or 'log a meeting with Dr. Jenkins today about Prodo-X safety')"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSendChatMessage(e)
                  }
                }}
              />
              <button
                type="submit"
                className="btn btn-primary btn-icon"
                disabled={loading || !chatInput.trim()}
              >
                <Send size={18} />
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  )
}
export default App
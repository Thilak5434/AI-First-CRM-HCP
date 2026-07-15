import { configureStore, createSlice } from '@reduxjs/toolkit'

const getTodayDate = () => {
  const d = new Date()
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const getCurrentTime = () => {
  const d = new Date()
  const hours = String(d.getHours()).padStart(2, '0')
  const minutes = String(d.getMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
}
const initialFormState = {
  id: null,
  hcp_id: '',
  hcp_name: '',
  interaction_type: 'Meeting',
  date: getTodayDate(),
  time: getCurrentTime(),
  attendees: [],
  topics_discussed: '',
  materials_shared: [],
  sentiment: 'Neutral'
}
const crmSlice = createSlice({
  name: 'crm',
  initialState: {
    currentForm: { ...initialFormState },
    hcpList: [],
    interactionsList: [],
    chatMessages: [
      {
        role: 'assistant',
        content: "Hello! I'm your CRM AI Assistant. Describe your interaction. I will extract fields as a proposal. Review them on the left and click 'Apply proposed changes' (then 'Log Interaction' if you want to save to DB)."
      }
    ],
    proposedForm: {},
    proposedComplianceReport: null,
    complianceReport: null,
    loading: false,
    error: null,
    toast: null,
  },
  reducers: {
    setFormField: (state, action) => {
      const { field, value } = action.payload
      state.currentForm[field] = value
      // If we are changing hcp_id, sync the hcp_name from hcpList
      if (field === 'hcp_id') {
        const selected = state.hcpList.find(h => h.id === Number(value))
        if (selected) {
          state.currentForm.hcp_name = selected.name
          // Auto add doctor to attendees if not present
          if (!state.currentForm.attendees.includes(selected.name)) {
            state.currentForm.attendees = [...state.currentForm.attendees, selected.name]
          }
        }
      }
    },
    updateFormState: (state, action) => {
      state.currentForm = { ...state.currentForm, ...action.payload }
    },
    resetForm: (state) => {
      state.currentForm = { ...initialFormState, date: getTodayDate(), time: getCurrentTime() }
      state.complianceReport = null
    },
    addChatMessage: (state, action) => {
      state.chatMessages.push(action.payload)
    },
    setHcpList: (state, action) => {
      state.hcpList = action.payload
    },
    setInteractionsList: (state, action) => {
      state.interactionsList = action.payload
    },
    setComplianceReport: (state, action) => {
      state.complianceReport = action.payload
    },
    setProposedForm: (state, action) => {
      state.proposedForm = action.payload
    },
    setProposedComplianceReport: (state, action) => {
      state.proposedComplianceReport = action.payload
    },
    clearProposed: (state) => {
      state.proposedForm = {}
      state.proposedComplianceReport = null
    },

    setLoading: (state, action) => {
      state.loading = action.payload
    },
    setError: (state, action) => {
      state.error = action.payload
    },
    setToast: (state, action) => {
      state.toast = action.payload
    },
    clearToast: (state) => {
      state.toast = null
    }
  }
})
export const {
  setFormField,
  updateFormState,
  resetForm,
  addChatMessage,
  setHcpList,
  setInteractionsList,
  setComplianceReport,
  setProposedForm,
  setProposedComplianceReport,
  clearProposed,
  setLoading,
  setError,
  setToast,
  clearToast
} = crmSlice.actions
const store = configureStore({
  reducer: {
    crm: crmSlice.reducer
  }
})
export default store
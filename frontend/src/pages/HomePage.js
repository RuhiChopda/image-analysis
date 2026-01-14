import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, FileText, Trash2, BookOpen, Database, FileStack } from "lucide-react";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const HomePage = () => {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [stats, setStats] = useState({ documents: 0, chunks: 0, faqs: 0 });
  const [seedingFAQs, setSeedingFAQs] = useState(false);

  useEffect(() => {
    fetchDocuments();
    fetchStats();
  }, []);

  const fetchDocuments = async () => {
    try {
      const response = await axios.get(`${API}/documents`);
      setDocuments(response.data);
    } catch (e) {
      console.error("Error fetching documents:", e);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API}/stats`);
      setStats(response.data);
    } catch (e) {
      console.error("Error fetching stats:", e);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith(".pdf")) {
      toast.error("Only PDF files are supported");
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      await axios.post(`${API}/upload-document`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Document uploaded and processed successfully!");
      fetchDocuments();
      fetchStats();
    } catch (error) {
      toast.error("Error uploading document: " + error.response?.data?.detail || error.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId) => {
    try {
      await axios.delete(`${API}/documents/${docId}`);
      toast.success("Document deleted successfully");
      fetchDocuments();
      fetchStats();
    } catch (error) {
      toast.error("Error deleting document");
    }
  };

  const seedFAQs = async () => {
    setSeedingFAQs(true);
    try {
      const response = await axios.post(`${API}/faqs/seed`);
      toast.success(response.data.message);
      fetchStats();
    } catch (error) {
      toast.error("Error seeding FAQs");
    } finally {
      setSeedingFAQs(false);
    }
  };

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12 pt-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <BookOpen className="w-12 h-12 text-white" />
            <h1 className="text-5xl font-bold text-white" style={{ fontFamily: 'Playfair Display, serif' }}>
              Student Study Assistant
            </h1>
          </div>
          <p className="text-xl text-white/90 max-w-2xl mx-auto" style={{ fontFamily: 'Inter, sans-serif' }}>
            AI-powered RAG chatbot to help you study smarter. Upload your course materials and get instant answers.
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="bg-white/95 backdrop-blur-sm border-0 shadow-xl" data-testid="stats-documents-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Documents</CardTitle>
              <FileText className="w-4 h-4 text-purple-600" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-purple-700">{stats.documents}</div>
            </CardContent>
          </Card>

          <Card className="bg-white/95 backdrop-blur-sm border-0 shadow-xl" data-testid="stats-chunks-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Text Chunks</CardTitle>
              <FileStack className="w-4 h-4 text-purple-600" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-purple-700">{stats.chunks}</div>
            </CardContent>
          </Card>

          <Card className="bg-white/95 backdrop-blur-sm border-0 shadow-xl" data-testid="stats-faqs-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">FAQs</CardTitle>
              <Database className="w-4 h-4 text-purple-600" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-purple-700">{stats.faqs}</div>
            </CardContent>
          </Card>
        </div>

        {/* Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Card className="bg-white/95 backdrop-blur-sm border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-gray-800">
                <Upload className="w-5 h-5" />
                Upload Study Materials
              </CardTitle>
              <CardDescription>Upload PDF documents to build your knowledge base</CardDescription>
            </CardHeader>
            <CardContent>
              <label htmlFor="file-upload">
                <Button
                  data-testid="upload-document-btn"
                  disabled={uploading}
                  className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold py-6 text-lg"
                  onClick={() => document.getElementById('file-upload').click()}
                >
                  {uploading ? "Processing..." : "Choose PDF File"}
                </Button>
              </label>
              <input
                id="file-upload"
                type="file"
                accept=".pdf"
                onChange={handleFileUpload}
                className="hidden"
              />
            </CardContent>
          </Card>

          <Card className="bg-white/95 backdrop-blur-sm border-0 shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-gray-800">
                <Database className="w-5 h-5" />
                Bonus Feature: External Data
              </CardTitle>
              <CardDescription>Load FAQs from external data source</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button
                data-testid="seed-faqs-btn"
                onClick={seedFAQs}
                disabled={seedingFAQs}
                className="w-full bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 text-white font-semibold py-6 text-lg"
              >
                {seedingFAQs ? "Loading..." : "Load FAQ Data"}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Document List */}
        <Card className="bg-white/95 backdrop-blur-sm border-0 shadow-xl">
          <CardHeader>
            <CardTitle className="text-gray-800">Your Documents</CardTitle>
            <CardDescription>Manage your uploaded study materials</CardDescription>
          </CardHeader>
          <CardContent>
            {documents.length === 0 ? (
              <div className="text-center py-8 text-gray-500" data-testid="no-documents-message">
                <FileText className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                <p>No documents uploaded yet. Upload your first document to get started!</p>
              </div>
            ) : (
              <div className="space-y-3">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    data-testid={`document-item-${doc.id}`}
                    className="flex items-center justify-between p-4 bg-gradient-to-r from-purple-50 to-pink-50 rounded-lg border border-purple-200 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-center gap-3">
                      <FileText className="w-5 h-5 text-purple-600" />
                      <div>
                        <p className="font-medium text-gray-800">{doc.filename}</p>
                        <p className="text-sm text-gray-600">
                          {doc.chunk_count} chunks • Uploaded {new Date(doc.upload_date).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <Button
                      data-testid={`delete-document-btn-${doc.id}`}
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(doc.id)}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Chat Button */}
        <div className="fixed bottom-8 right-8">
          <Button
            data-testid="start-chat-btn"
            onClick={() => navigate("/chat")}
            className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-semibold px-8 py-6 text-lg rounded-full shadow-2xl hover:shadow-purple-500/50 transition-all"
          >
            Start Chat Session
          </Button>
        </div>
      </div>
    </div>
  );
};

export default HomePage;
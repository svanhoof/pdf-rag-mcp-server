import React, { useState, useEffect } from 'react';
import {
  Button,
  FormControl,
  FormLabel,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  Stack,
  Tag,
  TagCloseButton,
  TagLabel,
  Text,
  useToast,
  Wrap,
  WrapItem,
} from '@chakra-ui/react';
import { updateDocumentMetadata, DOCUMENT_TYPES } from '../api/documents';

const MetadataEditor = ({ isOpen, onClose, document, onSave }) => {
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState('');
  const [publicationYear, setPublicationYear] = useState('');
  const [documentType, setDocumentType] = useState('');
  const [authors, setAuthors] = useState([]);
  const [newAuthor, setNewAuthor] = useState('');

  // Initialize form when document changes
  useEffect(() => {
    if (document) {
      setTitle(document.title || '');
      setPublicationYear(document.publication_year || '');
      setDocumentType(document.document_type || '');
      setAuthors(document.authors || []);
      setNewAuthor('');
    }
  }, [document]);

  const handleAddAuthor = () => {
    const trimmed = newAuthor.trim();
    if (trimmed && !authors.includes(trimmed)) {
      setAuthors([...authors, trimmed]);
      setNewAuthor('');
    }
  };

  const handleRemoveAuthor = (authorToRemove) => {
    setAuthors(authors.filter(a => a !== authorToRemove));
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddAuthor();
    }
  };

  const handleSave = async () => {
    if (!document) return;

    setSaving(true);
    try {
      const payload = {
        id: document.id,
      };

      // Only include changed fields
      const trimmedTitle = title.trim();
      if (trimmedTitle !== (document.title || '')) {
        payload.title = trimmedTitle || null;
      }

      const year = publicationYear ? parseInt(publicationYear, 10) : null;
      if (year !== document.publication_year) {
        payload.publication_year = year;
      }

      if (documentType !== (document.document_type || '')) {
        payload.document_type = documentType || null;
      }

      const currentAuthors = document.authors || [];
      if (JSON.stringify(authors) !== JSON.stringify(currentAuthors)) {
        payload.authors = authors.length > 0 ? authors : null;
      }

      // Only call API if there are changes
      if (Object.keys(payload).length > 1) {
        await updateDocumentMetadata(payload);
        toast({
          title: 'Metadata updated',
          description: `Metadata for ${document.filename} has been updated.`,
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
        if (onSave) onSave();
      }
      onClose();
    } catch (error) {
      console.error('Failed to update metadata:', error);
      toast({
        title: 'Update failed',
        description: error.response?.data?.detail || 'Failed to update document metadata',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setSaving(false);
    }
  };

  if (!document) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Edit Metadata: {document.filename}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <Stack spacing={4}>
            <FormControl>
              <FormLabel>Title</FormLabel>
              <Input
                placeholder="Document title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </FormControl>

            <FormControl>
              <FormLabel>Publication Year</FormLabel>
              <Input
                type="number"
                placeholder="e.g., 2024"
                value={publicationYear}
                onChange={(e) => setPublicationYear(e.target.value)}
                min={1900}
                max={2100}
              />
            </FormControl>

            <FormControl>
              <FormLabel>Document Type</FormLabel>
              <Select
                placeholder="Select document type"
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value)}
              >
                {DOCUMENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </option>
                ))}
              </Select>
            </FormControl>

            <FormControl>
              <FormLabel>Authors</FormLabel>
              <Wrap spacing={2} mb={2}>
                {authors.map((author, idx) => (
                  <WrapItem key={idx}>
                    <Tag size="md" colorScheme="blue" borderRadius="full">
                      <TagLabel>{author}</TagLabel>
                      <TagCloseButton onClick={() => handleRemoveAuthor(author)} />
                    </Tag>
                  </WrapItem>
                ))}
              </Wrap>
              <Input
                placeholder="Type author name and press Enter"
                value={newAuthor}
                onChange={(e) => setNewAuthor(e.target.value)}
                onKeyPress={handleKeyPress}
              />
              <Text fontSize="xs" color="gray.500" mt={1}>
                Press Enter to add an author
              </Text>
            </FormControl>
          </Stack>
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose}>
            Cancel
          </Button>
          <Button colorScheme="blue" onClick={handleSave} isLoading={saving}>
            Save
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default MetadataEditor;

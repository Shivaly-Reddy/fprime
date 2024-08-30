// ======================================================================
// \title  TraceLogger.hpp
// \author sreddy
// \brief  hpp file for TraceLogger component implementation class
// ======================================================================

#ifndef Svc_TraceLogger_HPP
#define Svc_TraceLogger_HPP

#include "Svc/TraceLogger/TraceLoggerComponentAc.hpp"
#include <Os/File.hpp>
#include <Fw/Types/Assert.hpp>
#include <Fw/Buffer/Buffer.hpp>

// some limits.h don't have PATH_MAX
#ifdef PATH_MAX
#define FILE_PATH_MAX PATH_MAX
#else
#define FILE_PATH_MAX 255
#endif

// some limits.h don't have NAME_MAX
#ifdef NAME_MAX
#define FILE_NAME_MAX NAME_MAX
#else
#define FILE_NAME_MAX 255
#endif

//Max size of the Trace buffer including metadata (id,timetag,arguments) 
static const FwSizeType FW_TRACE_MAX_SER_SIZE = (FW_TRACE_BUFFER_MAX_SIZE + sizeof(FwTraceIdType) + Fw::Time::SERIALIZED_SIZE);


namespace Svc {

class TraceLogger : public TraceLoggerComponentBase {
  public:
    // ----------------------------------------------------------------------
    // Component construction and destruction
    // ----------------------------------------------------------------------

    //! Construct TraceLogger object
    TraceLogger(const char* const compName  //!< The component name
    );
    
    //!  \brief Component initialization routine
    //!
    //!  The initialization function calls the initialization
    //!  routine for the base class.
    //!
    //!  \param queueDepth the depth of the message queue for the component
    //!  \param instance: instance identifier. Default: 0.
    void init(NATIVE_INT_TYPE queueDepth, NATIVE_INT_TYPE instance = 0);
    
    //!  \brief Set log file and max size
    //!
    //!  This is to create a log file to write all the trace buffers to.
    //!  The file will not be written to once the max size is hit.
    //!
    //!  \param fileName The name of the file to create.  Must be less than 80 characters.
    //!  \param maxSize The max size of the file
    //!
    //!  \return true if creating the file was successful, false otherwise
    void set_log_file(const char* fileName, const U32 maxSize=2048);
    
    //!  \brief Trace Logger configure method
    //!
    //!  The configure method stores the file name to log traces.
    //!
    //!  \param file file where traces are stored.
    void configure(const char* file);

    //! Destroy TraceLogger object
    ~TraceLogger();

  PRIVATE:
    // ----------------------------------------------------------------------
    // Handler implementations for user-defined typed input ports
    // ----------------------------------------------------------------------

    //! Handler implementation for TraceBufferLogger
    //!
    //! Logging Port
    //! Input Trace port to write to file
    void TraceBufferLogger_handler(FwIndexType portNum,        //!< The port number
                                   FwTraceIdType id,           //!< Trace ID
                                   Fw::Time& timeTag,          //!< Time Tag
                                   const Fw::TraceCfg::TraceType& type,  //!< The trace type argument
                                   Fw::TraceBuffer& args       //!< Buffer containing serialized trace entry
                                   ) override;

  PRIVATE:
    // ----------------------------------------------------------------------
    // Handler implementations for commands
    // ----------------------------------------------------------------------

    //! Handler implementation for command EnableTrace
    //!
    //! Enable or disable trace
    void EnableTrace_cmdHandler(FwOpcodeType opCode,  //!< The opcode
                                U32 cmdSeq,            //!< The command sequence number
                                bool enable) override;

    //! Handler implementation for command DumpTraceDp
    //!
    //! Dump Trace to a data product
    void DumpTraceDp_cmdHandler(FwOpcodeType opCode,  //!< The opcode
                                U32 cmdSeq            //!< The command sequence number
                                ) override;
    // ----------------------------------------------------------------------
    // Member Variables
    // ----------------------------------------------------------------------

    enum FileMode {
        CLOSED = 0,
        OPEN = 1
    };

    // The filename data:
    Os::File m_log_file; //Log file
    FileMode m_mode;    // file mode
    Fw::String m_fileName; //File name
    U32 m_maxFileSize; //max file size
    U32 m_byteCount; //current byte count of the file
    bool m_log_init; //Is logfile initialized
    bool m_enable_trace; //Is trace logging enabled
    U8 m_file_data[FW_TRACE_MAX_SER_SIZE]; //Holds a max size including metadata
    Fw::Buffer m_file_buffer;

    // ----------------------------------------------------------------------
    // File functions:
    // ----------------------------------------------------------------------
    void openFile(
    );

    void closeFile(
    );

    void write_log_file(
    U8* data,
    U32 size
    );

    };

}  // namespace Svc

#endif
